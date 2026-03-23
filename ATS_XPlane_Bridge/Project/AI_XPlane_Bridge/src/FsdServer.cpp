#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "Ws2_32.lib")

#include "FsdServer.h"
#include <sstream>

void FsdServer::start(int port) {
    WSADATA wsa; WSAStartup(MAKEWORD(2,2), &wsa);
    SOCKET srv = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = INADDR_ANY;
    bind(srv, (sockaddr*)&addr, sizeof(addr));
    listen(srv, 1);
    client = accept(srv, nullptr, nullptr);
}

void FsdServer::send(const AircraftState& ac) {
    if (client == INVALID_SOCKET) return;
    std::ostringstream o;
    o << "@N:" << ac.id << ":" << ac.lat << ":" << ac.lon << ":"
      << int(ac.alt_ft) << ":" << int(ac.yaw) << ":"
      << int(ac.tas) << "\r\n";
    auto s = o.str();
    ::send(client, s.c_str(), (int)s.size(), 0);
}