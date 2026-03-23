#pragma once
#include "AircraftManager.h"
#include "XPLMInstance.h"
#include <unordered_map>

class InstanceRenderer {
public:
    void sync(const AircraftManager& mgr);
    void draw();
private:
    std::unordered_map<std::string, XPLMInstanceRef> inst;
};