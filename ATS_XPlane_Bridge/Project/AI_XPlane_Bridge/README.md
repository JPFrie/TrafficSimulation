AI X-Plane Bridge
================

This project builds a Windows X-Plane plugin that:

- Injects AI aircraft via XPLMInstance
- Reads player aircraft position
- Exposes all traffic via an FSD-style feed (EuroScope)

Steps:
1. Download X-Plane Windows Plugin SDK
2. Extract it into thirdparty/XPlaneSDK
3. Build with CMake + Visual Studio 2022
4. Copy .xpl into X-Plane/Resources/plugins/AI_XPlane_Bridge/win_x64/