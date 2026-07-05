# Flash M5Cardputer Client firmware
Write-Host "=== Flash M5Cardputer Client ===" -ForegroundColor Cyan

$dir = "D:\project\firmware\devices\m5cardputer_client"
Set-Location $dir

# Try to find COM port
Write-Host "Scanning for Cardputer COM port..." -ForegroundColor Yellow
$ports = pio device list 2>&1 | Select-String -Pattern "(COM\d+)" | ForEach-Object { $_.Matches.Groups[1].Value }

$comPort = $null
foreach ($p in $ports) {
    Write-Host "  Found port: $p" -ForegroundColor Gray
    if ($comPort -eq $null) { $comPort = $p }
}

if ($comPort -eq $null) {
    $comPort = Read-Host "Enter COM port (e.g. COM3)"
}

Write-Host "Flashing on $comPort..." -ForegroundColor Green
pio run --target upload --upload-port $comPort
if ($LASTEXITCODE -ne 0) {
    Write-Host "Flash failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Flash OK! Starting serial monitor..." -ForegroundColor Green
Write-Host "Press Ctrl+C to exit monitor" -ForegroundColor Yellow
pio device monitor -p $comPort -b 115200
