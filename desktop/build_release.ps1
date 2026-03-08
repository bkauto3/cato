# Cato Desktop Build Script
# Sets up MSVC environment and runs npx tauri build

$MSVC_VER = '14.44.35207'
$SDK_VER = '10.0.26100.0'
$VS_BASE = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools'
$MSVC_BIN = "$VS_BASE\VC\Tools\MSVC\$MSVC_VER\bin\HostX64\x64"
$SDK_BIN = "C:\Program Files (x86)\Windows Kits\10\bin\$SDK_VER\x64"
$SDK_LIB = "C:\Program Files (x86)\Windows Kits\10\Lib\$SDK_VER"
$MSVC_LIB = "$VS_BASE\VC\Tools\MSVC\$MSVC_VER\lib\x64"
$MSVC_INC = "$VS_BASE\VC\Tools\MSVC\$MSVC_VER\include"
$SDK_INC = "C:\Program Files (x86)\Windows Kits\10\Include\$SDK_VER"

$env:PATH = "$MSVC_BIN;$SDK_BIN;$env:USERPROFILE\.cargo\bin;C:\Program Files\nodejs;C:\Program Files\Git\bin;$env:PATH"
$env:LIB = "$MSVC_LIB;$SDK_LIB\um\x64;$SDK_LIB\ucrt\x64"
$env:INCLUDE = "$MSVC_INC;$SDK_INC\um;$SDK_INC\ucrt;$SDK_INC\shared"

Write-Host "=== Cato Desktop Build ===" -ForegroundColor Cyan
Write-Host "MSVC: $MSVC_VER"
Write-Host "SDK:  $SDK_VER"

# Verify cl.exe is reachable
$clPath = "$MSVC_BIN\cl.exe"
if (-not (Test-Path $clPath)) {
    Write-Error "cl.exe not found at $clPath"
    exit 1
}
Write-Host "cl.exe: OK" -ForegroundColor Green

Set-Location "$PSScriptRoot"

Write-Host "`nInstalling npm dependencies..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -ne 0) { Write-Error "npm install failed"; exit 1 }

Write-Host "`nBuilding Tauri app..." -ForegroundColor Yellow
npx tauri build
if ($LASTEXITCODE -ne 0) { Write-Error "tauri build failed"; exit 1 }

Write-Host "`n=== Build Complete ===" -ForegroundColor Green
Write-Host "EXE:  src-tauri\target\release\cato-desktop.exe"
Write-Host "MSI:  src-tauri\target\release\bundle\msi\"
Write-Host "NSIS: src-tauri\target\release\bundle\nsis\"
