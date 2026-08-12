# 캐러셀 디스코드 봇 중지
#
# start-bot.ps1 이 남긴 락 파일의 PID 를 읽어 그 프로세스만 끝낸다.
# ⚠ node 프로세스를 통째로 죽이지 않는다 — 이 PC 에서는 매거진 봇 등 다른 node
#   프로세스가 함께 돌고 있어서, 이름으로 죽이면 남의 봇까지 멈춘다.

$ErrorActionPreference = "Stop"

$botDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$lockFile = Join-Path $botDir "data\bot.lock"

if (-not (Test-Path -LiteralPath $lockFile)) {
    Write-Host "실행 중이 아닙니다 (락 파일 없음)." -ForegroundColor Yellow
    exit 0
}

$botPid = (Get-Content -LiteralPath $lockFile | Select-Object -First 1)
$proc = Get-Process -Id ([int]$botPid) -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "PID $botPid 프로세스가 이미 없습니다. 락만 정리합니다." -ForegroundColor Yellow
    Remove-Item -LiteralPath $lockFile -Force
    exit 0
}
if ($proc.ProcessName -ne "node") {
    Write-Host "PID $botPid 는 node 가 아닙니다($($proc.ProcessName)). 건드리지 않습니다." -ForegroundColor Red
    exit 1
}

Stop-Process -Id $proc.Id -Force
Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
Write-Host "봇을 중지했습니다 (PID $botPid)." -ForegroundColor Cyan
Write-Host "감시 루프(start-bot.ps1) 창이 열려 있으면 그 창도 Ctrl+C 로 닫으세요." -ForegroundColor DarkGray
