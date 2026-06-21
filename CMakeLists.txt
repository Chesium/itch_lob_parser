cmake_minimum_required(VERSION 3.20)

project(itch_lob_parser LANGUAGES CXX)

add_library(itch_parser
  cpp/itch_parser.cpp
  cpp/itch_spec.cpp
)

target_include_directories(itch_parser
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/cpp
)

target_compile_features(itch_parser PUBLIC cxx_std_20)

add_executable(itch_cli cpp/itch_cli.cpp)
target_link_libraries(itch_cli PRIVATE itch_parser)
