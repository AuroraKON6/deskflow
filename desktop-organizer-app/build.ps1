$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $PSScriptRoot '.venv311\Scripts\python.exe'
$OutputRoot = Join-Path $ProjectRoot 'desktop-organizer-dist'

& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name 'DeskFlow' `
  --runtime-hook (Join-Path $PSScriptRoot 'pyi_rth_qt_clean_path.py') `
  --exclude-module 'PyQt5' `
  --exclude-module 'PySide6.Qt3DAnimation' `
  --exclude-module 'PySide6.Qt3DCore' `
  --exclude-module 'PySide6.Qt3DExtras' `
  --exclude-module 'PySide6.Qt3DInput' `
  --exclude-module 'PySide6.Qt3DLogic' `
  --exclude-module 'PySide6.Qt3DRender' `
  --exclude-module 'PySide6.QtBluetooth' `
  --exclude-module 'PySide6.QtCharts' `
  --exclude-module 'PySide6.QtDataVisualization' `
  --exclude-module 'PySide6.QtDesigner' `
  --exclude-module 'PySide6.QtGraphs' `
  --exclude-module 'PySide6.QtHelp' `
  --exclude-module 'PySide6.QtLocation' `
  --exclude-module 'PySide6.QtMultimedia' `
  --exclude-module 'PySide6.QtMultimediaWidgets' `
  --exclude-module 'PySide6.QtNfc' `
  --exclude-module 'PySide6.QtPdf' `
  --exclude-module 'PySide6.QtPdfWidgets' `
  --exclude-module 'PySide6.QtPositioning' `
  --exclude-module 'PySide6.QtQml' `
  --exclude-module 'PySide6.QtQuick' `
  --exclude-module 'PySide6.QtQuick3D' `
  --exclude-module 'PySide6.QtQuickWidgets' `
  --exclude-module 'PySide6.QtRemoteObjects' `
  --exclude-module 'PySide6.QtScxml' `
  --exclude-module 'PySide6.QtSensors' `
  --exclude-module 'PySide6.QtSerialBus' `
  --exclude-module 'PySide6.QtSerialPort' `
  --exclude-module 'PySide6.QtSpatialAudio' `
  --exclude-module 'PySide6.QtSql' `
  --exclude-module 'PySide6.QtStateMachine' `
  --exclude-module 'PySide6.QtSvg' `
  --exclude-module 'PySide6.QtTest' `
  --exclude-module 'PySide6.QtTextToSpeech' `
  --exclude-module 'PySide6.QtUiTools' `
  --exclude-module 'PySide6.QtVirtualKeyboard' `
  --exclude-module 'PySide6.QtWebEngineQuick' `
  --exclude-module 'PySide6.QtWebSockets' `
  --exclude-module 'PySide6.QtWebView' `
  --distpath $OutputRoot `
  --workpath (Join-Path $PSScriptRoot 'build') `
  --specpath $PSScriptRoot `
  --add-data "$(Join-Path $ProjectRoot 'desktop-organizer-concepts');desktop-organizer-concepts" `
  (Join-Path $PSScriptRoot 'main.py')

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE"
}

# Slim down the bundle: drop Qt pieces DeskFlow never uses.
$Internal = Join-Path $OutputRoot 'DeskFlow\_internal'
$QtRoot = Join-Path $Internal 'PySide6'
$LocaleDir = Join-Path $QtRoot 'translations\qtwebengine_locales'
$Removed = 0

function Remove-Quiet([string]$Path) {
  if (Test-Path $Path) {
    Remove-Item $Path -Recurse -Force -ErrorAction SilentlyContinue
    $script:Removed++
  }
}

# PDF renderer pulled in by the WebEngine hook; unused by DeskFlow
Remove-Quiet (Join-Path $QtRoot 'Qt6Pdf.dll')
Remove-Quiet (Join-Path $QtRoot 'Qt6Pdf.pyd')

# Software OpenGL fallback (20MB); hardware GPU is assumed
Remove-Quiet (Join-Path $QtRoot 'opengl32sw.dll')

# Chromium devtools + debug snapshot: not needed in a shipped app
Remove-Quiet (Join-Path $QtRoot 'resources\qtwebengine_devtools_resources.pak')
Remove-Quiet (Join-Path $QtRoot 'resources\v8_context_snapshot.debug.bin')

# Keep only zh/en webengine locales (53 language packs -> 4, saves ~27MB)
if (Test-Path $LocaleDir) {
  Get-ChildItem $LocaleDir -Filter '*.pak' | Where-Object {
    $_.Name -notmatch '^(zh|en)' -and $_.Name -notin @('zh-CN.pak', 'zh-TW.pak', 'en-GB.pak', 'en-US.pak')
  } | Remove-Item -Force -ErrorAction SilentlyContinue
}

# Keep only zh/en Qt translation files (saves ~5MB)
Get-ChildItem $QtRoot -Recurse -Filter 'qt_*.qm' -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -notmatch '^qt_(zh|en)[_-]'
} | Remove-Item -Force -ErrorAction SilentlyContinue

$DistSize = (Get-ChildItem (Join-Path $OutputRoot 'DeskFlow') -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Slimming removed {0} items; dist size now {1:N0} MB" -f $Removed, $DistSize)

Write-Host "Portable app created at: $(Join-Path $OutputRoot 'DeskFlow\DeskFlow.exe')"
