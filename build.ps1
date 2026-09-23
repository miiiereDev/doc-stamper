param(
  [ValidateSet("onefile","onedir","all")] $Target = "all"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Target -eq "onefile" -or $Target -eq "all") {
  Write-Host "Building single-file..." -ForegroundColor Cyan
  pyinstaller AutoStamper-OneFile.spec --noconfirm --clean
}
if ($Target -eq "onedir" -or $Target -eq "all") {
  Write-Host "Building onedir portable..." -ForegroundColor Cyan
  pyinstaller AutoStamper-Onedir.spec --noconfirm --clean
}
Write-Host "Done. Check dist/" -ForegroundColor Green
Get-ChildItem dist | Format-Table Name, LastWriteTime, @{N="Size (MB)";E={[math]::Round((Get-ChildItem $_ -Recurse | Measure-Object -Property Length -Sum).Sum/1MB,1)}}
