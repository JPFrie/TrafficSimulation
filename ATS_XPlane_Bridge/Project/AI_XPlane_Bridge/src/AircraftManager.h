#pragma once
#include <string>
#include <map>
#include <vector>
#include <unordered_map>
#include <unordered_set>

#include "XPLMDataAccess.h"
#include "XPLMUtilities.h"
#include "XPLMScenery.h"
#include "XPLMGraphics.h"
#include "XPLMInstance.h"

struct AircraftState {
    float lat = 0.0f;
    float lon = 0.0f;
    float alt_m = 0.0f;

    float pitch = 0.0f;
    float roll  = 0.0f;
    float yaw   = 0.0f;

    float cas   = 0.0f;
    float tas_mps = 0.0f;   // speed used for dead-reckoning
    float vs_mps  = 0.0f;

    float gs_north_mps = 0.0f;
    float gs_east_mps = 0.0f;
    float trk = 0.0f;

    float bank_angle = 0.0f;

    std::string model_key = "A320";
    std::string airline   = "";

    XPLMObjectRef   obj  = nullptr;
    XPLMInstanceRef inst = nullptr;
};

struct ManagedAircraft {
    // last two samples from network
    AircraftState prev;
    AircraftState next;

    double t_prev = 0.0;
    double t_next = 0.0;
    double last_rx = 0.0;

    bool has_prev = false;
    bool has_next = false;

    double rx = 0.0, ry = 0.0, rz = 0.0;
    double t_render = 0.0;
    bool   has_render = false;

    int missedPackets = 0;

    double vel_x = 0.0;
    double vel_z = 0.0;
    
    float ryaw  = 0.0f;
    float rroll = 0.0f;
    bool  has_att = false;

    double prev_rx = 0.0;
    double prev_rz = 0.0;

    // prev/next targets also in local coords (for smooth correction)
    double px = 0.0, py = 0.0, pz = 0.0;
    double nx = 0.0, ny = 0.0, nz = 0.0;

    double groundY = 0.0;
    bool hasGround = false;

    // model + x-plane resources
    std::string model_key = "A320";
    std::string airline   = "";
    XPLMObjectRef   obj  = nullptr;
    XPLMInstanceRef inst = nullptr;

    float gear_ratio = 0.0f;        // current animation state (0..1)
    float gear_target = 0.0f;       // desired state
    double gear_anim_start = 0.0;
    double gear_anim_duration = 5.0;
    bool gear_animating = false;
};

class AircraftManager {
public:
    void setModelBasePath(const std::string& base);
    void addCslRoot(const std::string& cslRoot);
    void buildCslCatalog();
    void updateAircraft(const std::string& id, const AircraftState& state);
    void applyPositions();
    void clear();
    void cleanupMissing(const std::unordered_set<std::string>& seenIds);

private:
    struct CslModel
    {
        std::string objPath;
        std::string texture;
        std::string textureLit;
    };
    XPLMObjectRef getOrLoadModel(const std::string& model_key, const std::string& airline_key);
    AircraftManager::CslModel lookupObjPathForIcao(const std::string& model_key, const std::string& airline) const;

    std::string mModelBasePath;
    std::vector<std::string> mCslRoots;
    std::unordered_map<std::string, std::string> mIcaoToObjPath;
    std::unordered_map<std::string, CslModel> mIcaoAirlineToModel;
    std::map<std::string, ManagedAircraft> mAircraft;
    std::map<std::string, XPLMObjectRef> mLoadedObjects;
    std::string mTempObjDir;

    std::unordered_map<std::string, std::string> mPatchedObjPaths;
    std::unordered_map<std::string, XPLMObjectRef> mPatchedObjects;

    std::string buildPatchedObj(
        const std::string& baseObjPath,
        const std::string& texture,
        const std::string& textureLit,
        const std::string& cacheKey
    );
};
