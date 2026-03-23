#pragma once
#include "AircraftManager.h"
#include <winsock2.h>

class FsdServer {
public:
    void start(int port);
    void send(const AircraftState& ac);
private:
    SOCKET client = INVALID_SOCKET;
};