#pragma once
#include <string>
#include <map>

#include "XPLMDataAccess.h"
#include "XPLMUtilities.h"
#include "XPLMScenery.h"
#include "XPLMGraphics.h"
#include "XPLMInstance.h"

struct AircraftState {
    float lat = 0.0f;
    float lon = 0.0f;
    float alt_ft = 0.0f;

    float pitch = 0.0f;
    float roll  = 0.0f;
    float yaw   = 0.0f;

    std::string model_key = "A320";

    XPLMObjectRef   obj  = nullptr;
    XPLMInstanceRef inst = nullptr;
};

class AircraftManager {
public:
    void setModelBasePath(const std::string& base);
    void updateAircraft(const std::string& id, const AircraftState& state);
    void applyPositions();
    void clear();

private:
    XPLMObjectRef getOrLoadModel(const std::string& model_key);

    std::string mModelBasePath;
    std::map<std::string, AircraftState> mAircraft;
    std::map<std::string, XPLMObjectRef> mLoadedObjects;
};
