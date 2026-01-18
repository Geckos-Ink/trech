# Define the target directory
$TargetDir = "thirds/torch"
if (!(Test-Path $TargetDir)) { New-Item -ItemType Directory -Path $TargetDir -Force }

Write-Host "Detecting platform: Windows"

# LibTorch URL for Windows (CPU, Release version)
$Url = "https://download.pytorch.org/libtorch/cpu/libtorch-win-shared-with-deps-latest.zip"
$ZipFile = "libtorch.zip"

# Download
Write-Host "Downloading LibTorch..."
Invoke-WebRequest -Uri $Url -OutFile $ZipFile

# Extract
Write-Host "Extracting to $TargetDir..."
Expand-Archive -Path $ZipFile -DestinationPath "temp_torch" -Force

# LibTorch zips usually contain a top-level 'libtorch' folder
Copy-Item -Path "temp_torch\libtorch\*" -Destination $TargetDir -Recurse -Force

# Cleanup
Remove-Item -Path "temp_torch" -Recurse -Force
Remove-Item -Path $ZipFile

Write-Host "Installation complete at $TargetDir"