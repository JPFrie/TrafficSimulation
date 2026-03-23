#pragma once
#include <cstdarg>
#include <cstdio>
#include <string>

#include "XPLMUtilities.h"

inline void XPLog(const char* fmt, ...) {
    char buf[2048]{};

    va_list args;
    va_start(args, fmt);
#if defined(_MSC_VER)
    vsnprintf_s(buf, sizeof(buf), _TRUNCATE, fmt, args);
#else
    vsnprintf(buf, sizeof(buf), fmt, args);
#endif
    va_end(args);

    XPLMDebugString(buf);
    XPLMDebugString("\n");
}
