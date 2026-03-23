#if defined(_WIN32)

    #define WIN32_LEAN_AND_MEAN
    #define NOMINMAX

    #include <winsock2.h>
    #include <ws2tcpip.h>
    #include <windows.h>

#elif defined(__linux__)

    #include <sys/socket.h>
    #include <arpa/inet.h>
    #include <unistd.h>

#endif

#include "Logger.h"
#include "AircraftManager.h"

#include <vector>
#include <string>
#include <sstream>
#include <cstring>
#include <cstdlib>   // std::atof
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <unordered_set>

#include "XPLMInstance.h"
#include "XPLMGraphics.h"
#include "XPLMPlugin.h"
#include "XPLMMenus.h"
#include "XPLMUtilities.h"
#include "XPLMProcessing.h"
#include "XPLMDataAccess.h"
#include "UdpReceiver.h"

namespace fs = std::filesystem;

#ifdef getline
#undef getline
#endif

// =====================
// Globals
// =====================
static XPLMMenuID gMenu = nullptr;
static int        gToggleItem = -1;

static bool       gRunning = false;
static UdpReceiver* gUdp = nullptr;
static AircraftManager gAircraftManager;
static int  gShowDebugItem = -1;
static bool gShowDebug     = false;

static float gLogTimer = 0.0f; // used to throttle logs

static XPLMObjectRef   gTestObj  = nullptr;
static XPLMInstanceRef gTestInst = nullptr;

static void* const MENU_STARTSTOP = (void*)1;
static void* const MENU_SHOWDEBUG = (void*)2;

static XPLMDataRef drOverridePlane = XPLMFindDataRef("sim/operation/override/override_planepath");
static XPLMDataRef drOverrideForces = XPLMFindDataRef("sim/operation/override/override_forces");

struct JumpTarget {
    std::string id;
    double lat;
    double lon;
    double alt_m;
};

static std::vector<JumpTarget> gJumpTargets;

// Menu
static XPLMMenuID gJumpMenu = nullptr;
static float gJumpMenuTimer = 0.0f;

// =====================
// Forward decls
// =====================
static void StartBridge();
static void StopBridge();
static void UpdateMenuCheck();
static void MenuHandler(void* inMenuRef, void* inItemRef);
static float FlightLoopCb(float inElapsedSinceLastCall,
                          float inElapsedTimeSinceLastFlightLoop,
                          int   inCounter,
                          void* inRefcon);

static float DebugLoopCb(float inElapsedSinceLastCall,
                         float /*inElapsedTimeSinceLastFlightLoop*/,
                         int   /*inCounter*/,
                         void* /*inRefcon*/);

static void UpdateMenuChecks();
static void ToggleDebug();
static void DestroyTestInstance();

static std::string upper(std::string s)
{
    std::transform(s.begin(), s.end(), s.begin(),
        [](unsigned char c){ return (char)std::toupper(c); });
    return s;
}

// =====================
// Menu + control
// =====================
static void UpdateMenuChecks() {
    if (!gMenu) return;

    if (gToggleItem >= 0) {
        XPLMCheckMenuItem(gMenu, gToggleItem,
                          gRunning ? xplm_Menu_Checked : xplm_Menu_Unchecked);
    }

    if (gShowDebugItem >= 0) {
        XPLMCheckMenuItem(gMenu, gShowDebugItem,
                          gShowDebug ? xplm_Menu_Checked : xplm_Menu_Unchecked);
    }
}

static void DestroyTestInstance()
{
    if (gTestInst) {
        XPLMDestroyInstance(gTestInst);
        gTestInst = nullptr;
        XPLog("[AI_XPlane_Bridge] DEBUG: Instance destroyed");
    }

    // Note: XPLMObjectRef doesn't have an unload call in X-Plane 11 SDK.
    // It's fine to keep gTestObj cached for the plugin lifetime.
}

static std::string GetPluginRootPath()
{
    char path[2048] = {0};
    XPLMGetPluginInfo(XPLMGetMyID(), nullptr, path, nullptr, nullptr);
    std::string p(path);

    // 1) strip filename (AI_XPlane_Bridge.xpl)
    auto pos = p.find_last_of("/\\");
    if (pos != std::string::npos) p = p.substr(0, pos);

    // now we're in .../win_x64

    // 2) go up one more -> .../AI_XPlane_Bridge
    pos = p.find_last_of("/\\");
    if (pos != std::string::npos) p = p.substr(0, pos);

    return p;
}

static void StartBridge() {
    if (gRunning) return;

    XPLog("[AI_XPlane_Bridge] START requested");

    // Create UDP receiver
    gUdp = new UdpReceiver(5005);

    // Register flight loop at ~50Hz (0.02s). Use 0 for "every frame".
    XPLMRegisterFlightLoopCallback(FlightLoopCb, 0.02f, nullptr);

    gRunning = true;
    UpdateMenuChecks();

    XPLog("[AI_XPlane_Bridge] STARTED");
}

static void StopBridge() {
    if (!gRunning) return;

    XPLog("[AI_XPlane_Bridge] STOP requested");

    XPLMUnregisterFlightLoopCallback(FlightLoopCb, nullptr);

    delete gUdp;
    gUdp = nullptr;

    gRunning = false;
    UpdateMenuChecks();

    XPLog("[AI_XPlane_Bridge] STOPPED");
}

static void JumpPlayerTo(double lat, double lon, double alt_m, float heading)
{
    static XPLMDataRef drLat   = XPLMFindDataRef("sim/flightmodel/position/latitude");
    static XPLMDataRef drLon   = XPLMFindDataRef("sim/flightmodel/position/longitude");
    static XPLMDataRef drAlt   = XPLMFindDataRef("sim/flightmodel/position/elevation");
    static XPLMDataRef drPsi   = XPLMFindDataRef("sim/flightmodel/position/psi");

    if (!drLat || !drLon || !drAlt || !drPsi) {
        XPLog("[AI_XPlane_Bridge] JumpPlayerTo: missing datarefs");
        return;
    }

    XPLMSetDatai(drOverridePlane, 1);
    XPLMSetDatai(drOverrideForces, 1);

    XPLMSetDatad(drLat, lat);
    XPLMSetDatad(drLon, lon);
    XPLMSetDatad(drAlt, alt_m);

    XPLMSetDataf(drPsi, 0.0f);

    XPLMSetDatai(drOverridePlane, 0);
    XPLMSetDatai(drOverrideForces, 0);

    XPLog("[AI_XPlane_Bridge] Player jumped to lat=%.6f lon=%.6f alt_m=%.1f",
          lat, lon, alt_m);
}

static void MenuHandler(void* /*inMenuRef*/, void* inItemRef)
{
    intptr_t idx = (intptr_t)inItemRef;
    if (idx >= 0 && idx < (intptr_t)gJumpTargets.size()) {

        const auto& jt = gJumpTargets[(size_t)idx];

        static XPLMDataRef drLat = XPLMFindDataRef("sim/flightmodel/position/latitude");
        static XPLMDataRef drLon = XPLMFindDataRef("sim/flightmodel/position/longitude");
        static XPLMDataRef drAlt = XPLMFindDataRef("sim/flightmodel/position/elevation");

        XPLMSetDatad(drLat, jt.lat);
        XPLMSetDatad(drLon, jt.lon);
        XPLMSetDatad(drAlt, jt.alt_m);

        JumpPlayerTo(jt.lat, jt.lon, jt.alt_m, 0.0f);

        XPLog(
            "[AI_XPlane_Bridge] Jumped to %s (%.6f %.6f)",
            jt.id.c_str(),
            jt.lat,
            jt.lon
        );
        return;
    }

    if (inItemRef == MENU_STARTSTOP) {
        if (!gRunning) StartBridge();
        else StopBridge();
    }
    else if (inItemRef == MENU_SHOWDEBUG) {
        ToggleDebug();
    }
}

// =====================
// Test functions for OBJ Instance
// =====================

static void CreateTestInstance()
{
    if (gTestInst) return;

    // Plugin-Pfad holen
    XPLMPluginID myId = XPLMGetMyID();
    char pluginPath[1024] = {};
    XPLMGetPluginInfo(myId, nullptr, pluginPath, nullptr, nullptr);

    // pluginPath zeigt auf .../win_x64/AI_XPlane_Bridge.xpl
    // Wir wollen .../AI_XPlane_Bridge/objects/test.obj
    std::string path(pluginPath);

    // bis zum letzten Slash/backslash abschneiden (Dateiname entfernen)
    size_t slash = path.find_last_of("/\\");
    if (slash != std::string::npos) path = path.substr(0, slash);

    // jetzt sind wir in .../win_x64
    // eine Ebene hoch -> .../AI_XPlane_Bridge
    slash = path.find_last_of("/\\");
    if (slash != std::string::npos) path = path.substr(0, slash);

    // OBJ Pfad anhängen
    path += "/Resources/Test/Test.obj";

    XPLog("[AI_XPlane_Bridge] TEST: Loading OBJ: %s", path.c_str());

    gTestObj = XPLMLoadObject(path.c_str());
    if (!gTestObj) {
        XPLog("[AI_XPlane_Bridge] TEST: Failed to load test OBJ");
        return;
    }

    const char* drefs[] = { nullptr };
    gTestInst = XPLMCreateInstance(gTestObj, drefs);

    XPLog("[AI_XPlane_Bridge] TEST: Instance created");
}

static void UpdateTestInstanceToPlayer()
{
    if (!gTestInst) return;

    static XPLMDataRef drLat = XPLMFindDataRef("sim/flightmodel/position/latitude");
    static XPLMDataRef drLon = XPLMFindDataRef("sim/flightmodel/position/longitude");
    static XPLMDataRef drAlt = XPLMFindDataRef("sim/flightmodel/position/elevation");
    static XPLMDataRef drHdg = XPLMFindDataRef("sim/flightmodel/position/psi");

    double lat = XPLMGetDatad(drLat);
    double lon = XPLMGetDatad(drLon);
    double alt = XPLMGetDatad(drAlt);   // meters MSL
    float  hdg = XPLMGetDataf(drHdg);

    double x, y, z;
    XPLMWorldToLocal(lat, lon, alt, &x, &y, &z);

    XPLMDrawInfo_t di{};
    di.structSize = sizeof(di);
    di.x = (float)x;
    di.y = (float)y;
    di.z = (float)z;
    di.heading = hdg;
    di.pitch = 0.0f;
    di.roll  = 0.0f;

    XPLMInstanceSetPosition(gTestInst, &di, nullptr);
}

void deletePatchedObjects(const std::string& dir)
{
    try
    {
        if (fs::exists(dir))
        {
            fs::remove_all(dir);
            XPLMDebugString("[AI_XPlane_Bridge] Deleted patched objs\n");
        }
    }
    catch (...)
    {
        XPLMDebugString("[AI_XPlane_Bridge] Failed to delete patched objs\n");
    }
}

// =====================
// FINISH Test functions for OBJ Instance
// =====================

static void RebuildJumpMenu()
{
    if (!gMenu) return;

    // Create submenu once
    if (!gJumpMenu) {
        gJumpMenu = XPLMCreateMenu(
        "Jump to Aircraft",
        gMenu,
        XPLMAppendMenuItem(gMenu, "Jump to Aircraft", nullptr, 0),
        MenuHandler,
        nullptr
    );
    }

    // Clear old entries
    XPLMClearAllMenuItems(gJumpMenu);

    // Add aircraft
    for (size_t i = 0; i < gJumpTargets.size(); ++i) {
        const auto& jt = gJumpTargets[i];

        char label[256];
        std::snprintf(
            label, sizeof(label),
            "%s (%.5f %.5f)",
            jt.id.c_str(),
            jt.lat,
            jt.lon
        );

        XPLMAppendMenuItem(
            gJumpMenu,
            label,
            (void*)(intptr_t)i,
            0
        );
    }
}

// =====================
// Flight loop (poll UDP)
// =====================
static float FlightLoopCb(float inElapsedSinceLastCall,
                          float /*inElapsedTimeSinceLastFlightLoop*/,
                          int   /*inCounter*/,
                          void* /*inRefcon*/)
{
    if (!gRunning || !gUdp) return 0.02f;
    std::unordered_set<std::string> seenThisFrame;
    // --- 1) UDP lesen (robust null-terminiert) ---
    char buf[4096];
    buf[0] = '\0';
    buf[sizeof(buf) - 1] = '\0';  // garantiert Terminator am Ende

    const bool got = gUdp->poll(buf, (int)sizeof(buf) - 1);
    if (got) {
        // Zusätzliche Sicherheit (falls poll exakt sizeof-1 Bytes schreibt):
        buf[sizeof(buf) - 1] = '\0';

        // Optional: RAW-Log ist sehr spammy -> ggf. throttlen
        XPLog("[AI_XPlane_Bridge] UDP packet received");
        // XPLog("[AI_XPlane_Bridge] RAW:\n%s", buf);

        // buf enthält mehrere Zeilen CSV
        std::istringstream iss{ std::string(buf) };
        std::string line;

        while (std::getline(iss, line)) {
            if (line.empty()) continue;

            // Falls CRLF: '\r' am Ende entfernen
            if (!line.empty() && line.back() == '\r')
                line.pop_back();

            if (line.empty()) continue;

            // XPLog("[AI_XPlane_Bridge] LINE: %s", line.c_str());

            std::istringstream ls{ line };
            std::string token;
            std::vector<std::string> p;
            p.reserve(12);

            while (std::getline(ls, token, ',')) {
                p.push_back(token);
            }

            if (p.size() < 8) {
                XPLog("[AI_XPlane_Bridge] INVALID LINE (fields=%d): %s",
                      (int)p.size(), line.c_str());
                continue;
            }

            const std::string id        = p[0];
            seenThisFrame.insert(id);
            std::string airline;
            if (id.size() >= 3)
                airline = upper(id.substr(0,3));
            const std::string model_key = p[1];

            AircraftState s{};
            s.model_key = model_key;
            s.airline = airline;
            s.lat    = (float)std::atof(p[2].c_str());
            s.lon    = (float)std::atof(p[3].c_str());
            s.alt_m = (float)std::atof(p[4].c_str()) * 0.3048;
            s.yaw    = (float)std::atof(p[5].c_str());
            s.cas  = (float)std::atof(p[6].c_str());
            s.pitch   = (float)std::atof(p[7].c_str());
            s.tas_mps   = (float)std::atof(p[8].c_str()) * 0.514444; // from kts in m/s
            s.vs_mps   = (float)std::atof(p[9].c_str()) * 0.00508; // from ft/min in m/s
            s.gs_north_mps    = (float)std::atof(p[10].c_str());
            s.gs_east_mps    = (float)std::atof(p[11].c_str());
            s.trk    = (float)std::atof(p[12].c_str());
            s.bank_angle    = (float)std::atof(p[13].c_str());

            gAircraftManager.updateAircraft(id, s);

            // Jump targets aktualisieren (alt_m korrekt aus ft)
            bool found = false;
            for (auto& jt : gJumpTargets) {
                if (jt.id == id) {
                    jt.lat = s.lat;
                    jt.lon = s.lon;
                    jt.alt_m = s.alt_m;
                    found = true;
                    break;
                }
            }

            if (!found) {
                gJumpTargets.push_back({
                    id,
                    s.lat,
                    s.lon,
                    (double)s.alt_m
                });
            }

            //XPLog("[AI_XPlane_Bridge] AC id=%s model=%s lat=%.6f lon=%.6f alt_m=%.1f hdg=%.1f p=%.1f r=%.1f",
            //      id.c_str(), model_key.c_str(),
            //      s.lat, s.lon, s.alt_m,
            //      s.yaw, s.cas, s.pitch);
        }
    }
    gAircraftManager.cleanupMissing(seenThisFrame);
    // --- 2) Positionen IMMER anwenden (nicht nur bei UDP) ---
    gAircraftManager.applyPositions();

    // --- 3) Jump-Menü regelmäßig neu bauen (auch wenn UDP pausiert) ---
    gJumpMenuTimer += inElapsedSinceLastCall;
    if (gJumpMenuTimer > 1.0f) {
        gJumpMenuTimer = 0.0f;
        RebuildJumpMenu();
    }

    return 0.02f;
}

static float DebugLoopCb(float /*inElapsedSinceLastCall*/,
                         float /*inElapsedTimeSinceLastFlightLoop*/,
                         int   /*inCounter*/,
                         void* /*inRefcon*/)
{
    if (!gShowDebug) return 0.25f; // keep it light

    // ensure instance exists
    CreateTestInstance();
    UpdateTestInstanceToPlayer();

    return 0.25f; // update 4 times/sec (enough for debug)
}

static void ToggleDebug()
{
    gShowDebug = !gShowDebug;

    if (gShowDebug) {
        XPLog("[AI_XPlane_Bridge] DEBUG: ShowDebug ON (spawn Test.obj at player)");

        CreateTestInstance();
        UpdateTestInstanceToPlayer();

        // start a small loop so it stays at player (optional, but useful)
        XPLMRegisterFlightLoopCallback(DebugLoopCb, 0.25f, nullptr);
    } else {
        XPLog("[AI_XPlane_Bridge] DEBUG: ShowDebug OFF");

        XPLMUnregisterFlightLoopCallback(DebugLoopCb, nullptr);
        DestroyTestInstance();
    }

    UpdateMenuChecks();
}

// =====================
// X-Plane Plugin API
// =====================
PLUGIN_API int XPluginStart(char* outName, char* outSig, char* outDesc) {
    std::strcpy(outName, "ATS_XPlane_Bridge");
    std::strcpy(outSig,  "jpf.ats_xplane_bridge");
    std::strcpy(outDesc, "AirTrafficSim (WSL) -> X-Plane bridge");
    XPLog("[AI_XPlane_Bridge] XPluginStart");

    // Create menu under Plugins
    XPLMMenuID pluginsMenu = XPLMFindPluginsMenu();
    int myItem = XPLMAppendMenuItem(pluginsMenu, "AI XPlane Bridge", nullptr, 0);
    gMenu = XPLMCreateMenu("AI XPlane Bridge", pluginsMenu, myItem, MenuHandler, nullptr);

    gToggleItem = XPLMAppendMenuItem(gMenu, "Start / Stop", MENU_STARTSTOP, 0);
    gShowDebugItem = XPLMAppendMenuItem(gMenu, "ShowDebug (spawn Test.obj at player)", MENU_SHOWDEBUG, 0);

    UpdateMenuChecks(); 

    // Default: not running until user starts it
    gRunning = false;

    std::string pluginRoot = GetPluginRootPath(); // falls du das schon hast
    gAircraftManager.setModelBasePath(pluginRoot);

    gAircraftManager.addCslRoot(pluginRoot + "/Resources/CSL");
    gAircraftManager.buildCslCatalog();

    XPLog("[AI_XPlane_Bridge] Loaded (use Plugins -> AI XPlane Bridge -> Start / Stop)");
    return 1;
}

PLUGIN_API void XPluginStop(void) {
    XPLog("[AI_XPlane_Bridge] XPluginStop");

    // Ensure everything stops cleanly
    StopBridge();
    deletePatchedObjects("Resources/plugins/AI_XPlane_Bridge/_patched_objs");
    if (gMenu) {
        XPLMDestroyMenu(gMenu);
        gMenu = nullptr;
        gToggleItem = -1;
    }

    if (gShowDebug) {
        gShowDebug = false;
        XPLMUnregisterFlightLoopCallback(DebugLoopCb, nullptr);
        DestroyTestInstance();
    }
}

PLUGIN_API int XPluginEnable(void) {
    XPLog("[AI_XPlane_Bridge] XPluginEnable");
    CreateTestInstance();
    return 1;
}

PLUGIN_API void XPluginDisable(void) {
    XPLog("[AI_XPlane_Bridge] XPluginDisable");
    // Optional: auto-stop when plugin is disabled via Plugin Admin
    StopBridge();
}

PLUGIN_API void XPluginReceiveMessage(XPLMPluginID /*inFrom*/, int /*inMsg*/, void* /*inParam*/) {
    // Keep empty unless you need it
}