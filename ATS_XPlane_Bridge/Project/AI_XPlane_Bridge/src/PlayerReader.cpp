#include "PlayerReader.h"
#include "XPLMDataAccess.h"

AircraftState PlayerReader::read() {
    static XPLMDataRef lat = XPLMFindDataRef("sim/flightmodel/position/latitude");
    static XPLMDataRef lon = XPLMFindDataRef("sim/flightmodel/position/longitude");
    static XPLMDataRef alt_m = XPLMFindDataRef("sim/flightmodel/position/elevation"); // meters MSL
    static XPLMDataRef hdg = XPLMFindDataRef("sim/flightmodel/position/psi");         // degrees true

    AircraftState s{};
    s.lat = (float)XPLMGetDatad(lat);
    s.lon = (float)XPLMGetDatad(lon);
    s.alt_m = (float)XPLMGetDatad(alt_m);
    s.pitch = 0.0f;
    s.roll  = 0.0f;
    s.yaw   = XPLMGetDataf(hdg);

    s.model_key = "PLAYER";
    return s;
}
