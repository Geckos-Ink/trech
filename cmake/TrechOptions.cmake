option(TRECH_ENABLE_GEANT4 "Build Geant4 simulation layer" ON)
option(TRECH_ENABLE_TORCH "Build LibTorch ML layer" OFF)
option(TRECH_ENABLE_DNA_CHEM "Enable Geant4-DNA chemistry wiring (when available)" OFF)
option(TRECH_FETCH_DEPS "Allow CMake to fetch third-party dependencies" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
