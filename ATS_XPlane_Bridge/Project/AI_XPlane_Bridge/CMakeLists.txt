cmake_minimum_required(VERSION 3.15)
project(AI_XPlane_Bridge)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(XPLANE_SDK "${CMAKE_SOURCE_DIR}/thirdparty/XPlaneSDK")

add_library(AI_XPlane_Bridge SHARED
    src/Plugin.cpp
    src/AircraftManager.cpp
    src/UdpReceiver.cpp
    src/PlayerReader.cpp
    src/UdpSender.cpp
)

target_include_directories(AI_XPlane_Bridge PRIVATE
    ${XPLANE_SDK}/CHeaders/XPLM
    ${XPLANE_SDK}/CHeaders/Widgets
    ${XPLANE_SDK}/include
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/src
)

target_compile_definitions(AI_XPlane_Bridge PRIVATE XPLM200)

set_target_properties(AI_XPlane_Bridge PROPERTIES
    PREFIX ""
    SUFFIX ".xpl"
)

if(WIN32)
    set(PLATFORM_LIB_DIR "${XPLANE_SDK}/Libraries/Win")
    target_compile_definitions(AI_XPlane_Bridge PRIVATE IBM=1)

    target_link_libraries(AI_XPlane_Bridge
        ${PLATFORM_LIB_DIR}/XPLM_64.lib
        ${PLATFORM_LIB_DIR}/XPWidgets_64.lib
        ws2_32
    )

elseif(UNIX AND NOT APPLE) # Linux
    set(PLATFORM_LIB_DIR "${XPLANE_SDK}/Libraries/Linux")
    target_compile_definitions(AI_XPlane_Bridge PRIVATE LIN=1)

    target_link_libraries(AI_XPlane_Bridge
        ${PLATFORM_LIB_DIR}/XPLM_64.so
        ${PLATFORM_LIB_DIR}/XPWidgets_64.so
        pthread
        dl
    )

elseif(APPLE)
    set(PLATFORM_LIB_DIR "${XPLANE_SDK}/Libraries/Mac")
    target_compile_definitions(AI_XPlane_Bridge PRIVATE APL=1)

    target_link_libraries(AI_XPlane_Bridge
        ${PLATFORM_LIB_DIR}/XPLM_64.dylib
        ${PLATFORM_LIB_DIR}/XPWidgets_64.dylib
    )
endif()