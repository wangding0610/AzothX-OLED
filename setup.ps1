param(
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Write-Host "== AzothX-OLED 依赖安装 =="
Write-Host "python: $((& $Python --version 2>&1))"
& $Python -m pip install --upgrade --quiet -r (Join-Path $root "requirements.txt")
Write-Host "依赖安装完成。"

Write-Host "`n== 自检：枚举 HID 通道 =="
Push-Location (Join-Path $root "tools")
& $Python oled.py list
Pop-Location

Write-Host "`n下一步： cd `"$root\tools`"  然后  python name.py"
