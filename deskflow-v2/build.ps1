$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$OutputRoot = Join-Path $PSScriptRoot 'dist'
$Concepts = Join-Path $ProjectRoot 'desktop-organizer-concepts'
$WV2Lib = Join-Path $PSScriptRoot '.venv\Lib\site-packages\webview\lib'

& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name 'DeskFlow' `
  --distpath $OutputRoot `
  --workpath (Join-Path $PSScriptRoot 'build') `
  --specpath $PSScriptRoot `
  --exclude-module 'PyQt5' `
  --exclude-module 'PySide6' `
  --exclude-module 'tkinter' `
  --exclude-module 'PyQt6' `
  --add-data "$Concepts;desktop-organizer-concepts" `
  --add-data "$WV2Lib\Microsoft.Web.WebView2.Core.dll;webview2lib" `
  --add-data "$WV2Lib\Microsoft.Web.WebView2.WinForms.dll;webview2lib" `
  --add-data "$WV2Lib\runtimes\win-x64\native\WebView2Loader.dll;webview2lib\runtimes\win-x64\native" `
  (Join-Path $PSScriptRoot 'DeskFlow.py')

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$DistSize = (Get-ChildItem (Join-Path $OutputRoot 'DeskFlow') -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host "v2 app built at: $(Join-Path $OutputRoot 'DeskFlow\DeskFlow.exe') ($([math]::Round($DistSize, 1)) MB)"
