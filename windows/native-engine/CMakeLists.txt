cmake_minimum_required(VERSION 3.21)
project(windows_music_lab_engine LANGUAGES CXX)
if(NOT WIN32 OR NOT MSVC)
    message(FATAL_ERROR "This fast rebuild project needs native MSVC x64 on Windows")
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(WML_BACKEND_BUILD "" CACHE PATH "Read-only existing native CUDA build")
get_filename_component(WML_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(WML_SOURCE "${WML_ROOT}/build")
if(NOT EXISTS "${WML_BACKEND_BUILD}/CMakeCache.txt")
    message(FATAL_ERROR "Provide WML_BACKEND_BUILD from a completed windows/Build.ps1 build")
endif()
execute_process(COMMAND git -C "${WML_ROOT}" rev-parse --short=12 HEAD
                OUTPUT_VARIABLE WML_VERSION OUTPUT_STRIP_TRAILING_WHITESPACE)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/version.h" "#pragma once\n#define YUE2_VERSION \"${WML_VERSION}-windows-full\"\n")
set(WML_LIBS
    "${WML_BACKEND_BUILD}/yyjson.lib"
    "${WML_BACKEND_BUILD}/vendor/cpp-httplib/httplib.lib"
    "${WML_BACKEND_BUILD}/ggml/src/ggml.lib"
    "${WML_BACKEND_BUILD}/ggml/src/ggml-cpu.lib"
    "${WML_BACKEND_BUILD}/ggml/src/ggml-cuda/ggml-cuda.lib"
    "${WML_BACKEND_BUILD}/ggml/src/ggml-base.lib")
foreach(lib IN LISTS WML_LIBS)
    if(NOT EXISTS "${lib}")
        message(FATAL_ERROR "Missing existing backend library: ${lib}")
    endif()
endforeach()
function(wml_target target)
    target_include_directories(${target} PRIVATE
        "${WML_SOURCE}" "${WML_SOURCE}/src" "${CMAKE_CURRENT_BINARY_DIR}"
        "${WML_SOURCE}/vendor/yyjson" "${WML_SOURCE}/vendor/cpp-httplib"
        "${WML_SOURCE}/ggml/include")
    target_compile_definitions(${target} PRIVATE GGML_MAX_NAME=128 GGML_SHARED
        GGML_BACKEND_SHARED GGML_USE_CPU GGML_USE_CUDA _CRT_SECURE_NO_WARNINGS)
    target_compile_options(${target} PRIVATE /W4 /wd4100 /wd4505 /utf-8)
endfunction()
add_library(wml_engine_support OBJECT "${WML_SOURCE}/src/request.cpp" "${WML_SOURCE}/src/model-store.cpp")
wml_target(wml_engine_support)
add_executable(yue-server "${WML_SOURCE}/tools/yue-server.cpp" $<TARGET_OBJECTS:wml_engine_support> "${WML_ROOT}/windows/utf8.manifest")
wml_target(yue-server)
target_link_libraries(yue-server PRIVATE ${WML_LIBS} ws2_32)
add_executable(engine-boundary-tests engine-boundary-tests.cpp $<TARGET_OBJECTS:wml_engine_support> "${WML_ROOT}/windows/utf8.manifest")
wml_target(engine-boundary-tests)
target_link_libraries(engine-boundary-tests PRIVATE ${WML_LIBS} ws2_32)
foreach(dll ggml-base.dll ggml-cpu.dll ggml-cuda.dll ggml.dll)
    if(NOT EXISTS "${WML_BACKEND_BUILD}/${dll}")
        message(FATAL_ERROR "Missing backend DLL: ${dll}")
    endif()
    configure_file("${WML_BACKEND_BUILD}/${dll}" "${CMAKE_CURRENT_BINARY_DIR}/${dll}" COPYONLY)
endforeach()
enable_testing()
add_test(NAME engine-boundary COMMAND engine-boundary-tests)
