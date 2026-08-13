$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$Concepts = Join-Path $ProjectRoot 'desktop-organizer-concepts'
$WV2Lib = Join-Path $PSScriptRoot '..\deskflow-v2\.venv\Lib\site-packages\webview\lib'
$OutDir = Join-Path $PSScriptRoot 'dist\DeskFlow'
$DistRoot = Join-Path $PSScriptRoot 'dist'

# references
$refs = @(
  'System.dll', 'System.Core.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll',
  'System.Web.Extensions.dll', 'System.Configuration.dll',
  "$WV2Lib\Microsoft.Web.WebView2.Core.dll",
  "$WV2Lib\Microsoft.Web.WebView2.WinForms.dll"
)
$refArgs = @()
foreach ($r in $refs) { $refArgs += "/reference:$r" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

& $Csc /nologo /target:winexe /platform:anycpu /optimize+ /out:"$OutDir\DeskFlow.exe" @refArgs "$PSScriptRoot\main.cs" | Out-String | Write-Host
if ($LASTEXITCODE -ne 0) { throw "csc failed: $LASTEXITCODE" }

# deploy WebView2 SDK + loader + concepts
Copy-Item "$WV2Lib\Microsoft.Web.WebView2.Core.dll" $OutDir -Force
Copy-Item "$WV2Lib\Microsoft.Web.WebView2.WinForms.dll" $OutDir -Force
Copy-Item "$WV2Lib\runtimes\win-x64\native\WebView2Loader.dll" $OutDir -Force
Copy-Item $Concepts $OutDir -Recurse -Force

$DistSize = (Get-ChildItem $OutDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host "v3 built at: $OutDir\DeskFlow.exe ($([math]::Round($DistSize, 2)) MB)"
