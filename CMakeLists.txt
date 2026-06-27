cmake_minimum_required(VERSION 3.30)

set(CMAKE_EXPERIMENTAL_CXX_IMPORT_STD "451f2fe2-a8a2-47c3-bc32-94786d8fc91b")
set(CMAKE_CXX_MODULE_STD ON)

project(itch_lob_parser LANGUAGES CXX)

add_library(itch_parser)

target_sources(itch_parser
  PUBLIC
    FILE_SET CXX_MODULES FILES
      cpp/itch_spec.cppm
      cpp/itch_parser.cppm
      cpp/lob.cppm
      cpp/itch.cppm
  PRIVATE
    cpp/itch_spec.cpp
    cpp/itch_parser.cpp
    cpp/lob.cpp
)

target_compile_features(itch_parser PUBLIC cxx_std_23)

if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  target_compile_options(itch_parser PRIVATE -fmodules)
endif()

add_executable(itch_cli cpp/itch_cli.cpp)
target_link_libraries(itch_cli PRIVATE itch_parser)
target_compile_features(itch_cli PRIVATE cxx_std_23)

if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  target_compile_options(itch_cli PRIVATE -fmodules)
endif()

set_property(TARGET itch_parser PROPERTY CXX_MODULE_STD ON)
set_property(TARGET itch_cli PROPERTY CXX_MODULE_STD ON)
