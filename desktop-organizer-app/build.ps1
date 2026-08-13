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

Write-Host "Portable app created at: $(Join-Path $OutputRoot 'DeskFlow\DeskFlow.exe')"
