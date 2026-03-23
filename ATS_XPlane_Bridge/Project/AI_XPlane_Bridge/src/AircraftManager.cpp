#include "AircraftManager.h"

#include <filesystem>
#include <fstream>
#include <cstdio>
#include <cstdlib>   // std::atof
#include <cstring>
#include <string>
#include <sstream>
#include <algorithm>
#include <cctype>
#include <chrono>
#include <random>
#include <unordered_set>

namespace fs = std::filesystem;

static XPLMDataRef gDrTotalTime = XPLMFindDataRef("sim/time/total_running_time_sec");

static constexpr double kEarthRadiusM = 6371000.0;
static constexpr double kPi = 3.1415926535897932384626433832795;

static double GetWallTime()
{
    using namespace std::chrono;
    static auto start = high_resolution_clock::now();
    return duration<double>(high_resolution_clock::now() - start).count();
}

static double GetSimTime()
{
    if (!gDrTotalTime)
        gDrTotalTime = XPLMFindDataRef("sim/time/total_running_time_sec");

    if (!gDrTotalTime)
        return 0.0;

    return (double)XPLMGetDataf(gDrTotalTime);
}

static float wrap360(float x) {
    while (x < 0.f) x += 360.f;
    while (x >= 360.f) x -= 360.f;
    return x;
}

static float shortestAngleDiff(float a, float b)
{
    float diff = fmodf(b - a + 540.0f, 360.0f) - 180.0f;
    return diff;
}

static float shortestDeltaDeg(float from, float to) {
    // returns delta in [-180, 180)
    float d = fmodf((to - from + 540.f), 360.f) - 180.f;
    return d;
}

static float moveTowards(float cur, float target, float maxStep) {
    float d = target - cur;
    if (d >  maxStep) return cur + maxStep;
    if (d < -maxStep) return cur - maxStep;
    return target;
}

static float moveTowardsAngleDeg(float curDeg, float targetDeg, float maxStepDeg) {
    curDeg = wrap360(curDeg);
    targetDeg = wrap360(targetDeg);

    float d = shortestDeltaDeg(curDeg, targetDeg);
    // clamp delta by maxStep
    if (d >  maxStepDeg) d =  maxStepDeg;
    if (d < -maxStepDeg) d = -maxStepDeg;

    return wrap360(curDeg + d);
}

namespace fs = std::filesystem;

static std::string trim(const std::string& s) {
    size_t a = 0, b = s.size();
    while (a < b && std::isspace((unsigned char)s[a])) a++;
    while (b > a && std::isspace((unsigned char)s[b-1])) b--;
    return s.substr(a, b-a);
}

static std::string upper(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
        [](unsigned char c){ return (char)std::toupper(c); });
    return s;
}

static void advanceLatLonMeters(double& lat_deg, double& lon_deg, double heading_deg, double dist_m)
{
    // small-step great-circle on a sphere (good enough for frame steps)
    double lat1 = lat_deg * kPi / 180.0;
    double lon1 = lon_deg * kPi / 180.0;
    double brng = heading_deg * kPi / 180.0;

    double dR = dist_m / kEarthRadiusM;

    double sinLat1 = sin(lat1);
    double cosLat1 = cos(lat1);
    double sinD = sin(dR);
    double cosD = cos(dR);

    double lat2 = asin(sinLat1 * cosD + cosLat1 * sinD * cos(brng));
    double lon2 = lon1 + atan2(sin(brng) * sinD * cosLat1,
                               cosD - sinLat1 * sin(lat2));

    lat_deg = lat2 * 180.0 / kPi;
    lon_deg = lon2 * 180.0 / kPi;
}

static float lerp(float a, float b, float t) {
    return a + (b - a) * t;
}

static float clamp01(float x) {
    if (x < 0.f) return 0.f;
    if (x > 1.f) return 1.f;
    return x;
}

static float lerpAngleDeg(float a, float b, float t) {
    auto wrap360 = [](float x){
        while (x < 0.f) x += 360.f;
        while (x >= 360.f) x -= 360.f;
        return x;
    };

    a = wrap360(a);
    b = wrap360(b);

    float d = fmodf((b - a + 540.f), 360.f) - 180.f; // shortest [-180,180)
    return wrap360(a + d * t);
}

static AircraftState interpolateState(const AircraftState& p, const AircraftState& n, float a) {
    AircraftState r{};
    r.model_key = n.model_key; // keep latest model
    r.lat   = lerp(p.lat,   n.lat,   a);
    r.lon   = lerp(p.lon,   n.lon,   a);
    r.alt_m = lerp(p.alt_m, n.alt_m, a);
    r.pitch = lerp(p.pitch, n.pitch, a);
    r.roll  = lerp(p.bank_angle,  n.bank_angle,  a);
    r.yaw   = lerpAngleDeg(p.yaw, n.yaw, a);
    return r;
}


static void Debug(const char* msg) {
    XPLMDebugString(msg);
    XPLMDebugString("\n");
}

void AircraftManager::setModelBasePath(const std::string& base) {
    mModelBasePath = base;

    mTempObjDir = base + "/_patched_objs";

    std::filesystem::create_directories(mTempObjDir);
}

void AircraftManager::addCslRoot(const std::string& cslRoot) {
    mCslRoots.push_back(cslRoot);
}

std::string pickRandomTexture(const fs::path& dir, const std::string& prefix)
{
    std::vector<std::string> matches;

    for (auto& entry : fs::directory_iterator(dir))
    {
        if (!entry.is_regular_file()) continue;

        std::string name = entry.path().filename().string();

        // match: DLH.png, DLH2.png, DLH3.png ...
        if (name.rfind(prefix, 0) == 0 && entry.path().extension() == ".png")
        {
            matches.push_back(name);
        }
    }

    if (matches.empty())
        return prefix + ".png"; // fallback

    // random auswählen
    static std::mt19937 rng{ std::random_device{}() };
    std::uniform_int_distribution<> dist(0, (int)matches.size() - 1);

    return matches[dist(rng)];
}

std::string AircraftManager::buildPatchedObj(
    const std::string& baseObjPath,
    const std::string& texture,
    const std::string& textureLit,
    const std::string& cacheKey)
{
    auto it = mPatchedObjPaths.find(cacheKey);
    if (it != mPatchedObjPaths.end())
        return it->second;

    std::ifstream in(baseObjPath);
    if (!in.is_open())
    {
        Debug(("[PATCH] failed to open base OBJ: " + baseObjPath).c_str());
        return "";
    }

    std::string patchedPath = mTempObjDir + "/" + cacheKey + ".obj";

    std::ofstream out(patchedPath);
    if (!out.is_open())
    {
        Debug(("[PATCH] failed to write OBJ: " + patchedPath).c_str());
        return "";
    }

    fs::path baseDir    = fs::path(baseObjPath).parent_path();
    fs::path patchedDir = fs::path(patchedPath).parent_path();

    bool textureWritten = false;
    bool textureLitWritten = false;

    std::string line;

    while (std::getline(in, line))
    {
        std::string trimmed = trim(line);

        std::istringstream iss(trimmed);
        std::string keyword;
        iss >> keyword;

        // ===============================
        // TEXTURE
        // ===============================
        if (keyword == "TEXTURE")
        {
            if (!texture.empty() && !textureWritten)
            {
                std::string texName = pickRandomTexture(baseDir, texture);

                fs::path texAbs = baseDir / texName;

                fs::path rel = fs::relative(texAbs, patchedDir);

                std::string texStr = rel.generic_string();

                out << "TEXTURE " << texStr << "\n";
                Debug(("PATCH TEXTURE: " + texStr).c_str());

                textureWritten = true;
            }

            continue;
        }

        // ===============================
        // TEXTURE_LIT
        // ===============================
        if (keyword == "TEXTURE_LIT")
        {
            if (!textureLit.empty() && !textureLitWritten)
            {
                fs::path litAbs = baseDir / textureLit;

                fs::path rel = fs::relative(litAbs, patchedDir);

                std::string litStr = rel.generic_string();

                out << "TEXTURE_LIT " << litStr << "\n";

                textureLitWritten = true;
            }

            continue;
        }

        out << line << "\n";
    }

    // fallback falls keine TEXTURE vorhanden
    if (!textureWritten && !texture.empty())
    {
        fs::path texAbs = baseDir / texture;
        fs::path rel = fs::relative(texAbs, patchedDir);

        out << "TEXTURE " << rel.generic_string() << "\n";
    }

    if (!textureLitWritten && !textureLit.empty())
    {
        fs::path litAbs = baseDir / textureLit;
        fs::path rel = fs::relative(litAbs, patchedDir);

        out << "TEXTURE_LIT " << rel.generic_string() << "\n";
    }

    in.close();
    out.close();

    Debug(("[PATCH] created: " + patchedPath).c_str());

    mPatchedObjPaths[cacheKey] = patchedPath;

    return patchedPath;
}

void AircraftManager::buildCslCatalog()
{
    mIcaoToObjPath.clear();
    mIcaoAirlineToModel.clear();

    int filesParsed = 0;
    int mappings    = 0;

    char sys[1024] = {};
    XPLMGetSystemPath(sys);
    fs::path xpRoot = fs::path(sys);

    for (const auto& root : mCslRoots)
    {
        fs::path rootPath(root);

        if (!fs::exists(rootPath))
        {
            Debug(("[AI_XPlane_Bridge] CSL root not found: " + root).c_str());
            continue;
        }

        for (auto& entry : fs::recursive_directory_iterator(rootPath))
        {
            if (!entry.is_regular_file()) continue;
            if (entry.path().filename() != "xsb_aircraft.txt") continue;

            filesParsed++;

            std::ifstream in(entry.path());
            if (!in.is_open()) continue;

            fs::path baseDir = entry.path().parent_path();

            std::string line;
            std::string currentObjToken;
            std::string currentAirline;
            std::string currentTexture;
            std::string currentTextureLit;
            std::vector<std::string> currentIcaos;

            auto normalizeObjToken = [](std::string s) -> std::string
            {
                s = trim(s);

                auto pos = s.find(':');
                if (pos == std::string::npos) return s;

                std::string left  = s.substr(0, pos);
                std::string right = s.substr(pos + 1);

                auto hasObjExt = [](const std::string& t)
                {
                    return t.size() >= 4 &&
                           (t.rfind(".obj")  == t.size() - 4 ||
                            t.rfind(".OBJ")  == t.size() - 4 ||
                            t.rfind(".obj8") == t.size() - 5 ||
                            t.rfind(".OBJ8") == t.size() - 5);
                };

                return hasObjExt(right) ? right : left;
            };

            auto commitBlock = [&]()
            {
                if (currentObjToken.empty() || currentIcaos.empty())
                    return;

                fs::path objAbs = baseDir / fs::path(currentObjToken).filename();

                if (!objAbs.has_extension())
                {
                    fs::path test = objAbs;
                    test += ".obj";
                    if (fs::exists(test))
                        objAbs = test;
                }

                if (!fs::exists(objAbs))
                {
                    Debug(("[AI_XPlane_Bridge] CSL OBJ not found: " +
                           objAbs.string()).c_str());
                    return;
                }

                fs::path objRel = fs::relative(objAbs, xpRoot);

                for (const auto& icao : currentIcaos)
                {
                    // Generic aircraft mapping
                    if (mIcaoToObjPath.find(icao) == mIcaoToObjPath.end())
                    {
                        mIcaoToObjPath[icao] = objRel.string();
                        mappings++;
                    }

                    // Airline specific mapping
                    if (!currentAirline.empty())
                    {
                        std::string key = icao + "_" + currentAirline;

                        CslModel model;
                        model.objPath = objRel.string();
                        model.texture = currentTexture;
                        model.textureLit = currentTextureLit;

                        mIcaoAirlineToModel[key] = model;
                        Debug(("CSL map: " + icao + "_" + currentAirline + " -> " + objRel.string()).c_str());
                    }
                }
            };

            while (std::getline(in, line))
            {
                line = trim(line);
                if (line.empty() || line[0] == '#') continue;

                std::istringstream iss(line);
                std::string key;
                iss >> key;
                key = upper(key);

                if (key == "OBJ8_AIRCRAFT" || key == "OBJ7_AIRCRAFT")
                {
                    commitBlock();
                    currentObjToken.clear();
                    currentAirline.clear();
                    currentTexture.clear();
                    currentTextureLit.clear();
                    currentIcaos.clear();

                    std::string token;
                    iss >> token; // z.B. A320:DLH

                    auto pos = token.find(':');

                    if (pos != std::string::npos)
                    {
                        std::string icao = upper(trim(token.substr(0, pos)));
                        std::string airline = upper(trim(token.substr(pos + 1)));

                        if (!icao.empty())
                            currentIcaos.push_back(icao);

                        if (!airline.empty())
                            currentAirline = airline;
                    }
                }
                else if (key == "OBJ8")
                {
                    std::string t1, t2, objToken, tex, texLit;
                    iss >> t1 >> t2 >> objToken >> tex >> texLit;

                    currentObjToken = normalizeObjToken(objToken);

                    if (!tex.empty())
                        currentTexture = tex;

                    if (!texLit.empty())
                        currentTextureLit = texLit;
                }
                else if (key == "ICAO")
                {
                    std::string icao;
                    iss >> icao;

                    icao = upper(trim(icao));

                    if (!icao.empty())
                        currentIcaos.push_back(icao);
                }
                else if (key == "AIRLINE")
                {
                    std::string icao, airline;
                    iss >> icao >> airline;

                    airline = upper(trim(airline));

                    if (!airline.empty())
                        currentAirline = airline;
                }
            }

            commitBlock();
        }
    }

    Debug(("[AI_XPlane_Bridge] CSL catalog built: " +
           std::to_string(filesParsed) + " files, " +
           std::to_string(mappings) + " mappings").c_str());
}

AircraftManager::CslModel AircraftManager::lookupObjPathForIcao(
    const std::string& model_key,
    const std::string& airline) const
{
    std::string icao = upper(model_key);
    std::string al   = upper(airline);

    Debug(("CSL LOOKUP INPUT: model=" + model_key + " airline=" + airline).c_str());

    // -------------------------
    // 1. Airline + Aircraft
    // -------------------------
    if (!al.empty())
    {
        std::string key = icao + "_" + al;

        auto it = mIcaoAirlineToModel.find(key);
        if (it != mIcaoAirlineToModel.end())
        {
            Debug(("CSL MATCH FOUND: " + key).c_str());
            return it->second;
        }
    }

    // -------------------------
    // 2. Generic Aircraft
    // -------------------------
    auto it2 = mIcaoToObjPath.find(icao);
    if (it2 != mIcaoToObjPath.end())
    {
        Debug(("CSL FALLBACK GENERIC: " + icao).c_str());

        CslModel m;
        m.objPath = it2->second;
        return m;
    }

    // -------------------------
    // 3. GLOBAL FALLBACK
    // -------------------------
    Debug("CSL FALLBACK GLOBAL: A320");

    auto it3 = mIcaoToObjPath.find("A320");
    if (it3 != mIcaoToObjPath.end())
    {
        CslModel m;
        m.objPath = it3->second;
        return m;
    }

    return CslModel{};
}

XPLMObjectRef AircraftManager::getOrLoadModel(
    const std::string& model_key,
    const std::string& airline_key)
{
    std::string cacheKey = model_key;

    if (!airline_key.empty())
        cacheKey += "_" + airline_key;

    // already loaded?
    auto it = mPatchedObjects.find(cacheKey);
    if (it != mPatchedObjects.end())
        return it->second;

    // lookup CSL
    CslModel model = lookupObjPathForIcao(model_key, airline_key);

    if (model.objPath.empty())
        return nullptr;

    // full path
    char sys[1024] = {};
    XPLMGetSystemPath(sys);
    std::filesystem::path xpRoot = std::filesystem::path(sys);

    std::filesystem::path fullObjPath = xpRoot / model.objPath;

    std::string objPath = fullObjPath.string();

    // 👉 PATCH wenn Textur vorhanden
    std::string finalPath = objPath;

    if (!model.texture.empty())
    {
        finalPath = buildPatchedObj(
            objPath,
            model.texture,
            model.textureLit,
            cacheKey
        );
    }

    if (finalPath.empty())
        return nullptr;

    // load
    XPLMObjectRef obj = XPLMLoadObject(finalPath.c_str());

    if (!obj)
    {
        Debug(("[LOAD] failed: " + finalPath).c_str());
        return nullptr;
    }

    mPatchedObjects[cacheKey] = obj;

    Debug(("[LOAD] OK: " + finalPath).c_str());

    return obj;
}

void AircraftManager::updateAircraft(const std::string& id, const AircraftState& state)
{
    const double now = GetWallTime();
    auto& ac = mAircraft[id];

    static constexpr double NET_DT = 1.0;

    ac.model_key = state.model_key;
    ac.airline   = state.airline;

    double sx=0, sy=0, sz=0;
    XPLMWorldToLocal((double)state.lat, (double)state.lon, (double)state.alt_m, &sx, &sy, &sz);

    if (!ac.has_render)
    {
        ac.rx = sx; ac.ry = sy; ac.rz = sz;
        ac.t_render = now;
        ac.has_render = true;

        ac.px = sx; ac.py = sy; ac.pz = sz;
        ac.nx = sx; ac.ny = sy; ac.nz = sz;

        ac.prev = state;
        ac.next = state;

        ac.t_prev = now;
        ac.t_next = now + NET_DT;

        ac.has_prev = true;
        ac.has_next = true;

        ac.ryaw  = state.yaw;
        ac.rroll = state.bank_angle;
        ac.has_att = true;

        return;
    }

    ac.px = ac.nx;
    ac.py = ac.ny;
    ac.pz = ac.nz;

    ac.prev = ac.next;

    ac.t_prev = now;
    ac.has_prev = true;

    ac.nx = sx;
    ac.ny = sy;
    ac.nz = sz;

    ac.next = state;
    ac.has_next = true;

    ac.t_next = ac.t_prev + NET_DT;
}

/*void AircraftManager::applyPositions()
{
    const double now = GetWallTime();
    float agl_m = 99999.0f;
    double groundRaw = 0.0;
    bool hitTerrain = false;

    // Shared terrain probe
    static XPLMProbeRef probe = nullptr;
    if (!probe) probe = XPLMCreateProbe(xplm_ProbeY);

    // Small helpers
    auto clamp01 = [](double x) {
        if (x < 0.0) return 0.0;
        if (x > 1.0) return 1.0;
        return x;
    };

    auto clampf = [](float v, float lo, float hi){ 
        return (v < lo) ? lo : (v > hi) ? hi : v; 
    };

    for (auto& kv : mAircraft) {
        auto& ac = kv.second;
        if (!ac.has_render) continue;

        // ============================================================
        // A) Dead-reckoning in X-Plane LOCAL meters using GS vector
        // ============================================================
        double dt = now - ac.t_render;
        if (dt < 0.0) dt = 0.0;
        if (dt > 0.2) dt = 0.2; // clamp long frame stalls (prevents big jumps)

        // X-Plane LOCAL axes:
        //   X = East (meters)
        //   Y = Up   (meters)
        //   Z = South(meters)
        
        const double gs_abs = std::sqrt(
            (double)ac.next.gs_east_mps  * (double)ac.next.gs_east_mps +
            (double)ac.next.gs_north_mps * (double)ac.next.gs_north_mps
        );

        // on_ground wenn Terrain getroffen & niedrig, sonst fallback über Geschwindigkeit
        const bool on_ground_dr =
            (hitTerrain && agl_m < 3.0f) ||
            (hitTerrain && agl_m < 10.0f && gs_abs < 25.0); // taxi/roll

        double vx = 0.0, vz = 0.0;

        // --- GROUND: GS vector (best for taxi) ---
        if (on_ground_dr) {
            // X=East, Z=South, North=-Z
            vx = (double)ac.next.gs_east_mps;
            vz = -(double)ac.next.gs_north_mps;
        }
        // --- AIR: TAS + Heading (best in cruise/climb/desc) ---
        else {
            // heading degrees -> unit vector
            const double hdg = (double)ac.next.yaw * 3.14159265358979323846 / 180.0;
            const double tas = (double)ac.next.tas_mps; // MUST exist in AircraftState

            const double east  = tas * std::sin(hdg);
            const double north = tas * std::cos(hdg);

            vx = east;
            vz = -north; // North=-Z
        }

        // Apply DR
        ac.rx += vx * dt;
        ac.rz += vz * dt;
        ac.ry += (double)ac.next.vs_mps * dt;

        ac.t_render = now;

        // ============================================================
        // B) Terrain probe + ground smoothing (prevents runway jitter)
        // ============================================================
        if (probe) {
            XPLMProbeInfo_t info{};
            info.structSize = sizeof(info);

            if (XPLMProbeTerrainXYZ(probe, ac.rx, ac.ry, ac.rz, &info) == xplm_ProbeHitTerrain) {
                groundRaw = (double)info.locationY;
                hitTerrain = true;

                // Smooth the ground height per aircraft
                if (!ac.hasGround) {
                    ac.groundY = groundRaw;
                    ac.hasGround = true;
                } else {
                    const double alpha = 0.05;
                    ac.groundY = ac.groundY + (groundRaw - ac.groundY) * alpha;
                }

                agl_m = (float)(ac.ry - ac.groundY);
            }
        }

        // Detect "on ground"
        const bool on_ground =
            (hitTerrain && agl_m < 3.0f) ||
            (hitTerrain && agl_m < 10.0f && std::fabs(ac.next.gs_north_mps) + std::fabs(ac.next.gs_east_mps) < 20.0f);

        // ============================================================
        // C) Soft correction towards target (local), tuned for ground/air
        // ============================================================
        if (ac.has_prev && ac.has_next && ac.t_next > ac.t_prev) {
            const double total = ac.t_next - ac.t_prev;
            double a = (total > 1e-6) ? (now - ac.t_prev) / total : 1.0;
            a = clamp01(a);

            // Linear local target between prev local (p*) and next local (n*)
            const double tx = ac.px + (ac.nx - ac.px) * a;
            const double ty = ac.py + (ac.ny - ac.py) * a;
            const double tz = ac.pz + (ac.nz - ac.pz) * a;

            // Gains: avoid micro-zitter on ground by using LOWER kPos but allow bigger maxCorr
            const double kPos    = on_ground ? 0.25 : 0.20;
            const double maxCorr = on_ground ? 6.0  : 20.0; // meters per frame

            // Clamp correction vector magnitude (horizontal)
            double dx = tx - ac.rx;
            double dz = tz - ac.rz;
            double d  = std::sqrt(dx*dx + dz*dz);

            if (d > maxCorr && d > 1e-6) {
                double s = maxCorr / d;
                dx *= s;
                dz *= s;
            }

            // Apply correction
            ac.rx += dx * kPos;
            ac.rz += dz * kPos;
            ac.ry += (ty - ac.ry) * kPos;

            // On-ground: clamp altitude to smoothed terrain to kill runway jitter
            if (on_ground && ac.hasGround) {
                ac.ry = ac.groundY + 0.5; // keep slightly above pavement
            }
        } else {
            // If we have no prev/next yet but we're on ground, still clamp height smoothly
            if (on_ground && ac.hasGround) {
                ac.ry = ac.groundY + 0.5;
            }
        }

        // ============================================================
        // D) Gear target + timed animation using AGL
        // CSL uses libxplanemp/controls/gear_ratio (0..1)
        // ============================================================
        // Recompute AGL after corrections (optional, but nicer)
        float agl2 = agl_m;
        if (probe && ac.hasGround) {
            agl2 = (float)(ac.ry - ac.groundY);
        }

        bool want_gear_down = false;

        // Down below ~2500 ft AGL (~762 m)
        if (hitTerrain && agl2 < 762.0f) want_gear_down = true;

        // Retract after takeoff: above 100 ft AGL (~30 m) and climbing
        if (hitTerrain && agl2 > 30.0f && ac.next.vs_mps > 0.5f) want_gear_down = false;

        const float desired = want_gear_down ? 1.0f : 0.0f;

        if (desired != ac.gear_target) {
            ac.gear_target = desired;
            ac.gear_anim_start = now;
            ac.gear_animating = true;
            ac.gear_anim_duration = 5.0; // seconds
        }

        if (ac.gear_animating) {
            const double dur = (ac.gear_anim_duration > 0.1) ? ac.gear_anim_duration : 0.1;
            double t = (now - ac.gear_anim_start) / dur;

            if (t >= 1.0) {
                ac.gear_ratio = ac.gear_target;
                ac.gear_animating = false;
            } else {
                t = clamp01(t);
                // smoothstep for hydraulic feel
                float tt = (float)t;
                float smooth = tt * tt * (3.0f - 2.0f * tt);

                if (ac.gear_target > ac.gear_ratio) ac.gear_ratio = smooth;        // extend
                else                                ac.gear_ratio = 1.0f - smooth; // retract
            }
        }

        // ============================================================
        // E) Ensure object + instance (gear_ratio instance dataref)
        // ============================================================
        if (!ac.obj) {
            ac.obj = getOrLoadModel(ac.model_key);
            if (!ac.obj) continue;
        }

        if (!ac.inst) {
            static const char* drefs[] = {
                "libxplanemp/controls/gear_ratio",
                nullptr
            };
            ac.inst = XPLMCreateInstance(ac.obj, drefs);
            if (!ac.inst) continue;
        }

        // ============================================================
        // F) Apply pose to X-Plane
        // ============================================================
        XPLMDrawInfo_t di;
        std::memset(&di, 0, sizeof(di));
        di.structSize = sizeof(di);

        di.x = (float)ac.rx;
        di.y = (float)ac.ry;
        di.z = (float)ac.rz;

        float targetYaw  = wrap360(ac.next.yaw);
        float targetRoll = clampf(ac.next.bank_angle, -60.0f, 60.0f);

        if (!ac.has_att)
        {
            ac.ryaw  = targetYaw;
            ac.rroll = targetRoll;
            ac.has_att = true;
        }

        const float dtf = (float)dt;
        const float maxRollRateDegPerSec = on_ground ? 8.0f  : 15.0f;
        const float maxYawRateDegPerSec  = on_ground ? 12.0f : 25.0f;
        
        ac.rroll = moveTowards(
            ac.rroll,
            targetRoll,
            maxRollRateDegPerSec * dtf
        );

        ac.ryaw = moveTowardsAngleDeg(
            ac.ryaw,
            targetYaw,
            maxYawRateDegPerSec * dtf
        );
        
        di.heading = ac.ryaw;
        di.roll    = ac.rroll;
        di.pitch   = 0.0f;

        // If you want pitch/roll, clamp them:
        // auto clampf = [](float v, float lo, float hi){ return (v<lo)?lo:(v>hi)?hi:v; };
        // di.pitch = clampf(ac.next.pitch, -30.0f, 30.0f);
        // di.roll  = clampf(ac.next.roll,  -60.0f, 60.0f);

        float drefValues[1] = { ac.gear_ratio };
        XPLMInstanceSetPosition(ac.inst, &di, drefValues);
    }
}*/

void AircraftManager::applyPositions()
{
    const double now = GetWallTime();
    static constexpr double SNAPSHOT_DELAY = 0.5;
    const double render_time = now - SNAPSHOT_DELAY; 

    static XPLMProbeRef probe = nullptr;
    if (!probe) probe = XPLMCreateProbe(xplm_ProbeY);

    auto clamp01 = [](double x){
        if (x < 0.0) return 0.0;
        if (x > 1.0) return 1.0;
        return x;
    };

    auto clampf = [](float v, float lo, float hi){
        return (v < lo) ? lo : (v > hi) ? hi : v;
    };

    for (auto& kv : mAircraft)
    {
        auto& ac = kv.second;
        if (!ac.has_render) continue;

        bool hitTerrain = false;
        double groundRaw = 0.0;
        float agl_m = 99999.0f;

        double dt = now - ac.t_render;
        if (dt < 0.0) dt = 0.0;
        //if (dt > 0.2) dt = 0.2;
        if (dt > 0.2) dt = 0.2;

        if (probe)
        {
            XPLMProbeInfo_t info{};
            info.structSize = sizeof(info);

            if (XPLMProbeTerrainXYZ(probe, ac.rx, ac.ry, ac.rz, &info) == xplm_ProbeHitTerrain)
            {
                groundRaw = info.locationY;
                hitTerrain = true;

                if (!ac.hasGround)
                {
                    ac.groundY = groundRaw;
                    ac.hasGround = true;
                }
                else
                {
                    const double alpha = 0.05;
                    ac.groundY += (groundRaw - ac.groundY) * alpha;
                }

                agl_m = (float)(ac.ry - ac.groundY);
            }
        }

        const double gs_abs = std::sqrt(
            ac.next.gs_east_mps * ac.next.gs_east_mps +
            ac.next.gs_north_mps * ac.next.gs_north_mps
        );

        const bool on_ground = hitTerrain && agl_m < 15.0f;

        char buf[128];
        sprintf(buf, "%s | GROUND %s\n",
            kv.first.c_str(),
            on_ground ? "YES" : "NO"
        );
        XPLMDebugString(buf);

        double vx = 0.0;
        double vz = 0.0;
        
        if (on_ground)
        {
            double gs = std::sqrt(
                ac.next.gs_east_mps * ac.next.gs_east_mps +
                ac.next.gs_north_mps * ac.next.gs_north_mps
            );

            double yaw_rad = ac.ryaw * kPi / 180.0;

            vx = gs * std::sin(yaw_rad);
            vz = -gs * std::cos(yaw_rad);
        }
        else
        {
            const double hdg = ac.next.yaw * 3.14159265358979323846 / 180.0;
            const double tas = ac.next.tas_mps;

            vx = tas * std::sin(hdg);
            vz = -tas * std::cos(hdg);
        }

        ac.rx += vx * dt;
        ac.rz += vz * dt;
        ac.ry += ac.next.vs_mps * dt;

        ac.t_render = now;

        ac.vel_x = vx;
        ac.vel_z = vz;

        if (ac.has_prev && ac.has_next && ac.t_next > ac.t_prev)
        {
            const double total = ac.t_next - ac.t_prev;

            double a = (total > 1e-6)
                ? (render_time - ac.t_prev) / total
                : 1.0;

            a = clamp01(a);

            const double tx = ac.px + (ac.nx - ac.px) * a;
            const double ty = ac.py + (ac.ny - ac.py) * a;
            const double tz = ac.pz + (ac.nz - ac.pz) * a;

            //const double kPos = on_ground ? 0.25 : 0.20;
            const double kPos = on_ground ? 0.02 : 0.015;
            const double maxCorr = on_ground ? 6.0 : 20.0;

            double dx = tx - ac.rx;
            double dz = tz - ac.rz;

            // limit correction per frame
            const double maxStep = 1.5;   // meters per frame

            double d = std::sqrt(dx*dx + dz*dz);

            if (d > maxStep)
            {
                dx *= maxStep / d;
                dz *= maxStep / d;
            }

            ac.rx += dx * kPos;
            ac.rz += dz * kPos;
            ac.ry += (ty - ac.ry) * kPos;

            if (on_ground && ac.hasGround)
                ac.ry = ac.groundY + 0.5;
        }

        // ------------------------------------------------
        // Gear animation
        // ------------------------------------------------

        bool want_gear_down = false;

        if (hitTerrain && agl_m < 762.0f)
            want_gear_down = true;

        if (hitTerrain && agl_m > 30.0f && ac.next.vs_mps > 0.5f)
            want_gear_down = false;

        const float desired = want_gear_down ? 1.0f : 0.0f;

        if (desired != ac.gear_target)
        {
            ac.gear_target = desired;
            ac.gear_anim_start = now;
            ac.gear_animating = true;
            ac.gear_anim_duration = 5.0;
        }

        if (ac.gear_animating)
        {
            const double dur = (ac.gear_anim_duration > 0.1) ? ac.gear_anim_duration : 0.1;
            double t = (now - ac.gear_anim_start) / dur;

            if (t >= 1.0)
            {
                ac.gear_ratio = ac.gear_target;
                ac.gear_animating = false;
            }
            else
            {
                t = clamp01(t);
                float tt = (float)t;
                float smooth = tt * tt * (3.0f - 2.0f * tt);

                if (ac.gear_target > ac.gear_ratio)
                    ac.gear_ratio = smooth;
                else
                    ac.gear_ratio = 1.0f - smooth;
            }
        }

        if (!ac.obj)
        {
            std::string model_key = ac.model_key;
            std::string airline_key = ac.airline;
            if (!ac.airline.empty()){
                ac.obj = getOrLoadModel(model_key, airline_key);
            }else{
                ac.obj = getOrLoadModel(model_key, "");
            }

            
            if (!ac.obj) continue;
        }

        if (!ac.inst)
        {
            static const char* drefs[] = {
                "libxplanemp/controls/gear_ratio",
                nullptr
            };

            ac.inst = XPLMCreateInstance(ac.obj, drefs);
            if (!ac.inst) continue;
        }
        // Heading aus aktueller Bewegung berechnen

        // Bewegung seit letztem Frame
        float targetRoll = clampf(ac.next.bank_angle, -60.0f, 60.0f);

        // Geschwindigkeit
        double gs = sqrt(ac.vel_x * ac.vel_x + ac.vel_z * ac.vel_z);

        // ------------------------------------------------
        // Turn prediction
        // ------------------------------------------------
        if (fabs(ac.next.bank_angle) > 0.5 && gs > 2.0)
        {
            double bank_rad = ac.next.bank_angle * kPi / 180.0;

            double turnRate =
                tan(bank_rad) * 9.81 / gs;   // rad/s

            ac.ryaw += turnRate * dt * 57.2958; // rad → deg
            ac.ryaw = wrap360(ac.ryaw);
        }

        // ------------------------------------------------
        // Heading aus Bewegung bestimmen
        // ------------------------------------------------
        float targetYaw = ac.ryaw;

        // nur leichte Korrektur zum Server Heading
        float serverYaw = wrap360(ac.next.yaw);

        float diff = shortestAngleDiff(ac.ryaw, serverYaw);

        if (fabs(diff) > 1.0f)
            targetYaw = wrap360(ac.ryaw + diff * 0.01f);
        else
            targetYaw = ac.ryaw;

        // ------------------------------------------------
        // Initialisierung
        // ------------------------------------------------
        if (!ac.has_att)
        {
            ac.ryaw  = targetYaw;
            ac.rroll = targetRoll;
            ac.has_att = true;
        }

        // ------------------------------------------------
        // Smoothing
        // ------------------------------------------------
        const float dtf = (float)dt;
        const float maxRollRateDegPerSec = on_ground ? 8.0f : 15.0f;
        const float maxYawRateDegPerSec  = on_ground ? 120.0f : 30.0f;

        ac.rroll = moveTowards(ac.rroll, targetRoll, maxRollRateDegPerSec * dtf);

        ac.ryaw = moveTowardsAngleDeg(
            ac.ryaw,
            targetYaw,
            maxYawRateDegPerSec * dtf
        );

        // DEBUG nur für DLH330
        if (kv.first == "DLH330")
        {
            char buf[256];
            sprintf(buf,
                "DLH330 YAW | target=%.2f | ryaw=%.2f | vel=(%.2f %.2f) | GS=(%.2f %.2f)\n",
                targetYaw,
                ac.ryaw,
                ac.vel_x,
                ac.vel_z,
                ac.next.gs_east_mps,
                ac.next.gs_north_mps
            );

            XPLMDebugString(buf);
        }

        XPLMDrawInfo_t di{};
        di.structSize = sizeof(di);

        di.x = (float)ac.rx;
        di.y = (float)ac.ry;
        di.z = (float)ac.rz;

        di.heading = ac.ryaw;
        di.roll    = ac.rroll;
        di.pitch   = 0.0f;

        float drefValues[1] = { ac.gear_ratio };

        XPLMInstanceSetPosition(ac.inst, &di, drefValues);
    }
}

void AircraftManager::clear() {
    // Destroy instances
    for (auto& kv : mAircraft) {
        auto& s = kv.second;
        if (s.inst) {
            XPLMDestroyInstance(s.inst);
            s.inst = nullptr;
        }
    }
    mAircraft.clear();
    mPatchedObjects.clear();
    mPatchedObjPaths.clear();
    std::filesystem::remove_all(mTempObjDir);
}

void AircraftManager::cleanupMissing(const std::unordered_set<std::string>& seenIds)
{
    for (auto it = mAircraft.begin(); it != mAircraft.end(); )
    {
        auto& ac = it->second;

        if (seenIds.find(it->first) != seenIds.end())
        {
            // gesehen → reset
            ac.missedPackets = 0;
            ++it;
        }
        else
        {
            // nicht gesehen → zählen
            ac.missedPackets++;

            if (ac.missedPackets > 1000)
            {
                if (ac.inst)
                {
                    XPLMDestroyInstance(ac.inst);
                    ac.inst = nullptr;
                }

                Debug(("Aircraft removed (missed packets): " + it->first).c_str());

                it = mAircraft.erase(it);
            }
            else
            {
                ++it;
            }
        }
    }
}
