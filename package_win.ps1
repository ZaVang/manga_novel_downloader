# Windows PowerShell Package Script
Write-Host "=== Windows App Packaging Script ===" -ForegroundColor Green

# Set UTF-8 encoding
$OutputEncoding = [System.Text.Encoding]::UTF8

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptDir
$OutputDir = Join-Path $ProjectRoot "dist\windows"
$AppName = "manga_novel_downloader"
$MainScript = "gui.py"
$IconFile = "icon.ico"

Write-Host "Project Root: $ProjectRoot" -ForegroundColor Yellow

# Clean old builds
Write-Host "Cleaning old builds..." -ForegroundColor Yellow
$PathsToClean = @(
    (Join-Path $ProjectRoot "build"),
    (Join-Path $ProjectRoot "dist"), 
    (Join-Path $ProjectRoot "$AppName.spec")
)

foreach ($path in $PathsToClean) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Removed: $path" -ForegroundColor Gray
    }
}

# Setup virtual environment
$VenvDir = Join-Path $ProjectRoot "venv_win"
$VenvActivate = Join-Path $VenvDir "Scripts\Activate.ps1"

if (-not (Test-Path $VenvActivate)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment!" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& $VenvActivate

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& python -m pip install --upgrade pip
& python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
& python -m pip install pyinstaller

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install dependencies!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Build PyInstaller command
Write-Host "Building Windows application..." -ForegroundColor Green

$IconPath = Join-Path $ProjectRoot $IconFile
$MangaPath = Join-Path $ProjectRoot "manga"
$NovelPath = Join-Path $ProjectRoot "novel"
$CachePath = Join-Path $ProjectRoot "novel_cache"
$IconsPath = Join-Path $ProjectRoot "icon.icns"
$MainPath = Join-Path $ProjectRoot $MainScript

& pyinstaller --noconfirm `
    --name $AppName `
    --onedir `
    --windowed `
    --icon $IconPath `
    --add-data "$MangaPath;manga" `
    --add-data "$NovelPath;novel" `
    --add-data "$CachePath;novel_cache" `
    --add-data "$IconPath;." `
    --add-data "$IconsPath;." `
    --hidden-import "PIL._tkinter_finder" `
    --hidden-import "PyQt6.sip" `
    --hidden-import "PyQt6.QtGui" `
    --hidden-import "PyQt6.QtWidgets" `
    --hidden-import "PyQt6.QtCore" `
    --distpath $OutputDir `
    $MainPath

# Check result
$ExePath = Join-Path $OutputDir "$AppName\$AppName.exe"
if (Test-Path $ExePath) {
    Write-Host "SUCCESS: Windows application built successfully!" -ForegroundColor Green
    Write-Host "Output directory: $OutputDir" -ForegroundColor Yellow
    Write-Host "Executable: $ExePath" -ForegroundColor Yellow
} else {
    Write-Host "FAILED: Build failed!" -ForegroundColor Red
    Write-Host "Check the error messages above" -ForegroundColor Red
}

Write-Host "=== Build Complete ===" -ForegroundColor Green
Read-Host "Press Enter to exit"