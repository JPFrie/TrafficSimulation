#include "InstanceRenderer.h"
#include "XPLMScenery.h"

static const char* REFS[] = {
    "sim/flightmodel/position/latitude",
    "sim/flightmodel/position/longitude",
    "sim/flightmodel/position/elevation",
    "sim/flightmodel/position/phi",
    "sim/flightmodel/position/theta",
    "sim/flightmodel/position/psi"
};

void InstanceRenderer::sync(const AircraftManager& mgr) {
    for (auto& [id, ac] : mgr.all()) {
        if (ac.isPlayer) continue;
        if (!inst.count(id)) {
            auto obj = XPLMLoadObject("Aircraft/A320/A320CFM.obj");
            inst[id] = XPLMCreateInstance(obj, REFS);
        }
    }
}

void InstanceRenderer::draw() {}