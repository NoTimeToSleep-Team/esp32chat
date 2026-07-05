# Level 3 Build Report

## Firmware Binaries

| Device | Status | Size |
|--------|--------|------|
| M5Cardputer Client | ✅ Built | 908960 bytes |
| M5StickC Plus 2 | ✅ Built | 955776 bytes |

## Files Created

| File | Description |
|------|-------------|
| `D:\project\rpi-setup.sh` | RPi AP setup (hostapd + dnsmasq + captive portal) |
| `D:\project\rpi-deploy-server.sh` | Deploy LC server on RPi |
| `D:\project\server\scripts\seed_test_users.py` | Seed device user (login: device, pass: devicepass) |
| `D:\project\flash-cardputer.ps1` | Flash & serial monitor for Cardputer |
| `D:\project\flash-stickc.ps1` | Flash & serial monitor for StickC |
| `D:\project\flash-all.ps1` | Flash both devices sequentially |
| `D:\project\firmware\devices\m5cardputer_client\platformio.ini` | PIO config for Cardputer |
| `D:\project\firmware\devices\m5stickc_plus2\platformio.ini` | PIO config for StickC |

## Network Config (hardcoded in firmware)

| Parameter | Value |
|-----------|-------|
| SSID | LC-Hub (open, no password) |
| Server URL | http://192.168.4.1:18080 |
| Device login | device |
| Device password | devicepass |

## Next Steps

### Phase A: RPi Setup

1. Connect RPi via Ethernet to your router
2. Find RPi IP (check router admin page or Pi Connect)
3. Copy files to RPi (replace `<rpi-ip>` with actual IP):
   ```
   scp -r D:\project\server pi@<rpi-ip>:~/lc-server
   scp D:\project\rpi-setup.sh pi@<rpi-ip>:~/
   scp D:\project\rpi-deploy-server.sh pi@<rpi-ip>:~/
   ```
4. SSH into RPi and run setup:
   ```
   ssh pi@<rpi-ip>
   chmod +x ~/rpi-setup.sh ~/rpi-deploy-server.sh
   sudo ~/rpi-setup.sh
   sudo reboot
   ```
5. After reboot — connect your PC to Wi-Fi 'LC-Hub'
6. SSH to 192.168.4.1 and deploy server:
   ```
   ssh pi@192.168.4.1
   cd ~/lc-server
   ~/rpi-deploy-server.sh
   ```
7. Verify: open http://192.168.4.1:18080/docs

### Phase B: Flash Devices

1. Open PowerShell as Admin on this PC
2. Connect PC to LC-Hub Wi-Fi
3. Run master flash script:
   ```
   D:\project\flash-all.ps1
   ```
4. Follow prompts — plug each device via USB when asked
5. Check serial output for:
   - `wifi connected`
   - `auth ready`
   - `health status=200`
   - `auth_login status=200`
   - `chat_list / blog_list / support_list OK`

### Phase C: Verify Integration

1. Open http://192.168.4.1:18080/docs
2. Check GET /ops/system-health — shows uptime, CPU, RAM
3. Create a chat message via API
4. Run Level 2 sweep:
   ```
   cd D:\project
   python docs/tools/run_software_verification_sweep.py
   ```
