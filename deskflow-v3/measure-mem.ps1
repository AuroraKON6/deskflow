param([string]$Name = "DeskFlow")
$df = Get-Process -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $df) { "NOT RUNNING"; exit }
$all = Get-CimInstance Win32_Process
$desc = @{}
function Get-Desc([int]$parentId) {
  $all | Where-Object { $_.ParentProcessId -eq $parentId } | ForEach-Object {
    if (-not $desc.ContainsKey($_.ProcessId)) { $desc[$_.ProcessId] = $true; Get-Desc $_.ProcessId }
  }
}
Get-Desc $df.Id
$hostMB = $df.WorkingSet64 / 1MB
$rows = @()
foreach ($id in $desc.Keys) {
  $p = Get-Process -Id $id -ErrorAction SilentlyContinue
  if ($p) { $rows += [PSCustomObject]@{ Name = $p.ProcessName; Id = $id; MB = [math]::Round($p.WorkingSet64/1MB,0); Cmd = ((Get-CimInstance Win32_Process -Filter "ProcessId=$id").CommandLine) } }
}
"Host($Name)=$([math]::Round($hostMB,0))MB; WebView2=$($rows.Count)procs=$([math]::Round(($rows | Measure-Object MB -Sum).Sum,0))MB; TOTAL=$([math]::Round($hostMB + ($rows | Measure-Object MB -Sum).Sum,0))MB"
$rows | Sort-Object MB -Descending | ForEach-Object {
  $cmd = if ($_.Cmd) { $_.Cmd.Substring(0, [Math]::Min(90, $_.Cmd.Length)) } else { "" }
  "  pid=$($_.Id) $($_.MB)MB  $cmd"
}
