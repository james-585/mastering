cmake_minimum_required(VERSION 3.15)

project(suno_dsp LANGUAGES CXX)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(suno_dsp src_cpp/spectral_repair.cpp)

target_compile_features(suno_dsp PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(suno_dsp PRIVATE /O2 /fp:fast)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    target_compile_options(suno_dsp PRIVATE -O3 -ffast-math)
endif()
