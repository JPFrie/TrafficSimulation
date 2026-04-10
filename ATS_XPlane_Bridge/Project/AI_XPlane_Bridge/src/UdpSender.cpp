#include "UdpSender.h"

#if defined(_WIN32)
    #include <windows.h>
#else
    #include <unistd.h>
#endif

#include <cstring>

UdpSender::UdpSender(const char* ip, int port)
{
    mSock = socket(AF_INET, SOCK_DGRAM, 0);
    setTarget(ip, port);
}

UdpSender::~UdpSender()
{
#if defined(_WIN32)
    closesocket(mSock);
#else
    close(mSock);
#endif
}

void UdpSender::setTarget(const char* ip, int port)
{
    memset(&mAddr, 0, sizeof(mAddr));
    mAddr.sin_family = AF_INET;
    mAddr.sin_port = htons(port);
    inet_pton(AF_INET, ip, &mAddr.sin_addr);
}

void UdpSender::send(const char* msg)
{
    if (!msg) return;

    sendto(
        mSock,
        msg,
        (int)strlen(msg),
        0,
        (sockaddr*)&mAddr,
        sizeof(mAddr)
    );
}