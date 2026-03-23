#pragma once

#if defined(_WIN32)

    #define WIN32_LEAN_AND_MEAN
    #include <winsock2.h>
    #include <ws2tcpip.h>

    using SocketType = SOCKET;
    constexpr SocketType INVALID_SOCKET_VALUE = INVALID_SOCKET;

#else

    #include <sys/socket.h>

    using SocketType = int;
    constexpr SocketType INVALID_SOCKET_VALUE = -1;

#endif


class UdpReceiver {
public:
    explicit UdpReceiver(int port);
    ~UdpReceiver();

    // Returns true if a packet was received, and fills outBuffer with a null-terminated string.
    bool poll(char* outBuffer, int outBufferSize);

private:
    SocketType mSock = INVALID_SOCKET_VALUE;
};