AI X-Plane Bridge
================

This project builds a Windows X-Plane plugin that:

- Injects AI aircraft via XPLMInstance
- Model Matching via CSL database
- Interpolation of UDP package data (position etc.)
- Animation of CSL anim objects
- Future version: Override of X-Plane TCAS
- Future version: Reads player aircraft position
- Future Version: Exposes all traffic via an FSD-style feed (EuroScope)

Steps:
1. Download X-Plane Windows Plugin SDK
2. Extract it into thirdparty/XPlaneSDK
3. Build with CMake + Visual Studio 2017
4. Copy .xpl into X-Plane/Resources/plugins/AI_XPlane_Bridge/win_x64/ or /lin_x64/
