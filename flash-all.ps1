# Flash all devices sequentially
Write-Host "===== Level 3: Flash All Devices =====" -ForegroundColor Magenta
Write-Host ""

Write-Host "[Step 1/2] Plug in M5Cardputer Client via USB" -ForegroundColor Cyan
Read-Host "Press Enter when ready"
& "D:\project\flash-cardputer.ps1"

Write-Host ""
Write-Host "[Step 2/2] Now plug in M5StickC Plus 2 via USB" -ForegroundColor Cyan
Read-Host "Press Enter when ready"
& "D:\project\flash-stickc.ps1"

Write-Host ""
Write-Host "===== Done! Check server for device registrations =====" -ForegroundColor Green
Write-Host "Server API: http://192.168.4.1:18080/docs" -ForegroundColor White
