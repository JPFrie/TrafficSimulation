#pragma once

#if defined(_WIN32)
    #include <winsock2.h>
    #include <ws2tcpip.h>
#else
    #include <arpa/inet.h>
#endif

class UdpSender {
public:
    UdpSender(const char* ip, int port);
    ~UdpSender();

    void send(const char* msg);
    void setTarget(const char* ip, int port);

private:
#if defined(_WIN32)
    SOCKET mSock;
#else
    int mSock;
#endif
    sockaddr_in mAddr{};
};