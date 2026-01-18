#!/bin/bash

# Define the target directory
TARGET_DIR="thirds/torch"
mkdir -p "$TARGET_DIR"

# Detect OS
OS_TYPE=$(uname -s | tr '[:upper:]' '[:lower:]' )
ARCH_TYPE=$(uname -m)

echo "Detecting platform: $OS_TYPE ($ARCH_TYPE)"

# Determine Download URL (Stable 2.x CPU version)
# Note: LibTorch usually provides x86_64 for Linux/Windows and handles ARM via specialized builds.
if [[ "$OS_TYPE" == "linux" ]]; then
    URL="https://download.pytorch.org/libtorch/cpu/libtorch-shared-with-deps-latest.zip"
elif [[ "$OS_TYPE" == "darwin" ]]; then
    # macOS (M1/M2 use arm64, older use x86_64)
    URL="https://download.pytorch.org/libtorch/cpu/libtorch-macos-latest.zip"
else
    echo "Unsupported OS: $OS_TYPE"
    exit 1
fi

# Download and Extract
echo "Downloading LibTorch from $URL..."
curl -L "$URL" -o "libtorch.zip"

echo "Extracting to $TARGET_DIR..."
unzip -q libtorch.zip
# Move contents to thirds/torch and cleanup
cp -R libtorch/* "$TARGET_DIR"
rm -rf libtorch libtorch.zip

echo "Installation complete: $(ls $TARGET_DIR)"