$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$ServerUrl = if ($env:SERVER_URL) { $env:SERVER_URL } else { "https://openclaw.ciaobella.cc/doubao" }
$RoomId = if ($env:ROOM_ID) { $env:ROOM_ID } else { "doubao-win-test" }
$Trigger = if ($env:TRIGGER) { $env:TRIGGER } else { "archive" }
$Transport = if ($env:TRANSPORT) { $env:TRANSPORT } else { "stream" }
$RequestTimeoutSeconds = if ($env:REQUEST_TIMEOUT_SECONDS) { $env:REQUEST_TIMEOUT_SECONDS } else { "12" }
$StreamMaxTimeSeconds = if ($env:STREAM_MAX_TIME_SECONDS) { $env:STREAM_MAX_TIME_SECONDS } else { "90" }
$IntervalSeconds = if ($env:INTERVAL_SECONDS) { $env:INTERVAL_SECONDS } else { "0.25" }
$CurlResolve = if ($env:CURL_RESOLVE) { $env:CURL_RESOLVE } else { "openclaw.ciaobella.cc:443:172.67.208.237" }
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Set-Location $ProjectRoot

Write-Host "Starting Windows clipboard helper"
Write-Host "server_url=$ServerUrl"
Write-Host "room_id=$RoomId"
Write-Host "trigger=$Trigger"
Write-Host "request_timeout_seconds=$RequestTimeoutSeconds"
Write-Host "stream_max_time_seconds=$StreamMaxTimeSeconds"
Write-Host "interval_seconds=$IntervalSeconds"
Write-Host "curl_resolve=$CurlResolve"
Write-Host "transport=$Transport"
Write-Host "mode=clipboard"

$HelperArgs = @(
    "scripts/windows_paste_helper.py",
    "--server-url", $ServerUrl,
    "--room-id", $RoomId,
    "--interval-seconds", $IntervalSeconds,
    "--mode", "clipboard",
    "--trigger", $Trigger,
    "--transport", $Transport,
    "--request-timeout-seconds", $RequestTimeoutSeconds,
    "--stream-max-time-seconds", $StreamMaxTimeSeconds
)

if ($CurlResolve) {
    $HelperArgs += @("--curl-resolve", $CurlResolve)
}

& $Python @HelperArgs
exit $LASTEXITCODE
