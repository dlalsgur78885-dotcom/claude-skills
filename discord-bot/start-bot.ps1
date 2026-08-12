# 캐러셀 디스코드 봇 실행기
#
# 그냥 npm start 로 띄우면 터미널을 닫을 때 같이 죽고, 크래시하면 조용히 멈춘다.
# 이 스크립트는 죽으면 다시 띄우고, 두 번 뜨는 것을 막는다.
#
# 사용:  .\start-bot.ps1
# 중지:  .\stop-bot.ps1   (또는 이 창에서 Ctrl+C)

$ErrorActionPreference = "Stop"

$botDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $botDir

$envFile  = Join-Path $botDir ".env"
$dataDir  = Join-Path $botDir "data"
$lockFile = Join-Path $dataDir "bot.lock"
$logFile  = Join-Path $dataDir "bot.log"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env 파일이 없습니다. .env.example 을 복사해 값을 채우세요."
}
if (-not (Test-Path -LiteralPath $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
}

# ── 중복 실행 방지 ────────────────────────────────────────────────
# 봇이 둘 뜨면 모든 메시지에 답이 두 번 온다. 락 파일에 PID 를 적고,
# 그 PID 가 실제로 살아있는 node 인지 확인한다(PC 를 강제 종료하면 락만
# 남을 수 있으므로, 죽은 PID 의 락은 무시하고 덮어쓴다).
if (Test-Path -LiteralPath $lockFile) {
    $oldPid = (Get-Content -LiteralPath $lockFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid) {
        $alive = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($alive -and $alive.ProcessName -eq "node") {
            Write-Host "이미 실행 중입니다 (PID $oldPid). 중지하려면 .\stop-bot.ps1" -ForegroundColor Yellow
            exit 1
        }
    }
    Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
}

# ── 로그가 무한정 커지지 않게 ──────────────────────────────────────
if ((Test-Path -LiteralPath $logFile) -and ((Get-Item $logFile).Length -gt 5MB)) {
    Move-Item -LiteralPath $logFile -Destination "$logFile.old" -Force
}

Write-Host "캐러셀 봇을 시작합니다. 중지하려면 Ctrl+C." -ForegroundColor Cyan
Write-Host "로그: $logFile" -ForegroundColor DarkGray

# ── 감시 루프 ─────────────────────────────────────────────────────
# 즉시 죽는 경우(토큰 오류 등)에 초당 수십 번 재시작하면 로그만 쌓이고
# 디스코드 쪽에서도 좋을 게 없다. 실패가 이어지면 간격을 늘린다.
$delay = 3
try {
    while ($true) {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -LiteralPath $logFile -Value "`n[$stamp] --- 봇 시작 ---"

        $proc = Start-Process -FilePath "node" -ArgumentList "src/index.js" `
            -NoNewWindow -PassThru `
            -RedirectStandardOutput "$logFile.out" -RedirectStandardError "$logFile.err"

        Set-Content -LiteralPath $lockFile -Value $proc.Id
        $proc.WaitForExit()

        # 자식이 남긴 출력을 본 로그로 합친다(리다이렉트는 파일을 덮어쓰므로 매번 옮긴다)
        foreach ($part in @("$logFile.out", "$logFile.err")) {
            if (Test-Path -LiteralPath $part) {
                Get-Content -LiteralPath $part | Add-Content -LiteralPath $logFile
                Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
            }
        }

        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $msg = "[$stamp] 봇이 종료됨 (exit $($proc.ExitCode)). ${delay}초 뒤 다시 시작합니다."
        Add-Content -LiteralPath $logFile -Value $msg
        Write-Host $msg -ForegroundColor Yellow

        Start-Sleep -Seconds $delay
        # 30초까지만 늘린다. 일시적 네트워크 문제면 그 안에 회복된다.
        $delay = [Math]::Min($delay * 2, 30)
    }
}
finally {
    Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
    Write-Host "봇을 중지했습니다." -ForegroundColor Cyan
}
