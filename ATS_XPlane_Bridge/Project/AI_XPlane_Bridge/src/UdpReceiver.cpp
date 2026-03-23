#include "UdpReceiver.h"
#include "Logger.h"
#include <iostream>

#if defined(_WIN32)
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #include <windows.h>
#else
    #include <sys/socket.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #include <fcntl.h>
    #include <errno.h>
#endif


// =====================
// Constructor
// =====================
UdpReceiver::UdpReceiver(int port) {

#if defined(_WIN32)
    WSADATA wsa{};
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        XPLog("[AI_XPlane_Bridge] WSAStartup failed");
        return;
    }
#endif

    mSock = socket(AF_INET, SOCK_DGRAM, 0);

    if (mSock == INVALID_SOCKET_VALUE) {
#if defined(_WIN32)
        XPLog("[AI_XPlane_Bridge] socket() failed: %d", WSAGetLastError());
#else
        XPLog("[AI_XPlane_Bridge] socket() failed (errno=%d)", errno);
#endif
        return;
    }

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons((uint16_t)port);

    if (bind(mSock, (sockaddr*)&addr, sizeof(addr)) < 0) {
#if defined(_WIN32)
        XPLog("[AI_XPlane_Bridge] bind() failed: %d", WSAGetLastError());
        closesocket(mSock);
        WSACleanup();
#else
        XPLog("[AI_XPlane_Bridge] bind() failed (errno=%d)", errno);
        close(mSock);
#endif
        mSock = INVALID_SOCKET_VALUE;
        return;
    }

    // =====================
    // Non-blocking
    // =====================
#if defined(_WIN32)
    u_long nonBlocking = 1;
    ioctlsocket(mSock, FIONBIO, &nonBlocking);
#else
    int flags = fcntl(mSock, F_GETFL, 0);
    fcntl(mSock, F_SETFL, flags | O_NONBLOCK);
#endif

    XPLog("[AI_XPlane_Bridge] UDP listening on 0.0.0.0:%d", port);
}


// =====================
// Destructor
// =====================
UdpReceiver::~UdpReceiver() {

    if (mSock != INVALID_SOCKET_VALUE) {
#if defined(_WIN32)
        closesocket(mSock);
        WSACleanup();
#else
        close(mSock);
#endif
        mSock = INVALID_SOCKET_VALUE;
    }
}


// =====================
// Poll
// =====================
bool UdpReceiver::poll(char* outBuffer, int outBufferSize) {
    if (!outBuffer || outBufferSize <= 2) return false;
    if (mSock == INVALID_SOCKET_VALUE) return false;

    sockaddr_in from{};
#if defined(_WIN32)
    int fromLen = sizeof(from);
#else
    socklen_t fromLen = sizeof(from);
#endif

    int r = recvfrom(
        mSock,
        outBuffer,
        outBufferSize - 1,
        0,
        (sockaddr*)&from,
        &fromLen
    );

    if (r > 0) {
        outBuffer[r] = '\0';
        return true;
    }

    // =====================
    // Non-blocking handling
    // =====================
#if defined(_WIN32)
    if (WSAGetLastError() == WSAEWOULDBLOCK) return false;
#else
    if (errno == EWOULDBLOCK || errno == EAGAIN) return false;
#endif

    return false;
}