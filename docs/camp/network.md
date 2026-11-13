# Camp Wi-Fi access point

Camp Edition does **not** create a Wi-Fi network by itself. The application is a
web server; on-site the access point is provided by the Raspberry Pi (or another
Linux host) with `hostapd` + `dnsmasq`. This keeps the chat and camp UI working
without internet.

## Target scheme

```
phones / tablets / kiosks
        |  Wi-Fi: CAMP-CHAT (WPA2)
        v
Raspberry Pi 5  wlan0 = 192.168.50.1/24
  hostapd  -> access point
  dnsmasq  -> DHCP + local DNS (camp.local, chat.local, wildcard)
  FastAPI  -> http://192.168.50.1:18080/camp
        |  (optional) eth0 -> internet only if CAMP_AP_NAT_ENABLED=1
```

Defaults are offline: clients can reach the camp server, but not the internet.
This is intentional for child safety and predictable behaviour.

## One-command setup

On the Raspberry Pi, from the repository root:

```bash
sudo CAMP_AP_PASSPHRASE='replace-with-strong-pass' \
  bash server/scripts/configure_camp_ap.sh
```

Or from `server/`:

```bash
sudo CAMP_AP_PASSPHRASE='replace-with-strong-pass' \
  bash ./scripts/configure_camp_ap.sh
```

The wrapper uses `server/scripts/configure_pi_ap_nat.sh` and sets camp defaults:

| Setting | Default |
|---|---|
| SSID | `CAMP-CHAT` |
| Password | required, 8–63 chars, WPA2-PSK |
| Pi address | `192.168.50.1/24` |
| DHCP range | `192.168.50.50`–`192.168.50.150` |
| Portal | `http://192.168.50.1:18080/camp` |
| DNS | all names → `192.168.50.1`, plus `camp.local` / `chat.local` |
| NAT / internet | off |

### Optional settings

```bash
sudo \
  CAMP_AP_SSID='CAMP-2026' \
  CAMP_AP_PASSPHRASE='...' \
  CAMP_AP_COUNTRY='RU' \
  CAMP_AP_CHANNEL=6 \
  CAMP_AP_ADDRESS=192.168.50.1 \
  CAMP_AP_WLAN_IFACE=wlan0 \
  CAMP_PORTAL_PORT=18080 \
  bash server/scripts/configure_camp_ap.sh
```

With internet uplink (only if the camp policy allows it):

```bash
sudo \
  CAMP_AP_PASSPHRASE='...' \
  CAMP_AP_NAT_ENABLED=1 \
  CAMP_AP_UPLINK_IFACE=eth0 \
  CAMP_AP_DNS_SERVERS='1.1.1.1 8.8.8.8' \
  bash server/scripts/configure_camp_ap.sh
```

To keep an env file instead of long commands, create a root-owned file and pass
it explicitly:

```bash
sudo install -m 600 /dev/null /etc/camp-edition/ap.env
sudo editor /etc/camp-edition/ap.env
sudo CAMP_AP_ENV=/etc/camp-edition/ap.env bash server/scripts/configure_camp_ap.sh
```

## Verify

```bash
ip addr show wlan0
systemctl status hostapd --no-pager
systemctl status dnsmasq --no-pager
```

Then on a phone:

1. Connect to `CAMP-CHAT`.
2. Open `http://192.168.50.1:18080/camp` (or `http://camp.local:18080/camp`).
3. Log in with a camp web token and check `/camp/status` → network block.

Expected: no internet; `hostapd` active; phone gets an address from
`192.168.50.50–150`; the portal opens.

## Security

- Use WPA2-PSK with a strong password; rotate it per session or when staff
  change. Never leave the AP open.
- The default mode has no internet. Do not enable NAT unless the camp's policy
  and parental information explicitly allow it.
- Firewall the Pi so clients can reach only the portal/API (and DNS/DHCP);
  block SSH and admin ports from the AP interface.
- Treat the Wi-Fi password as an operational secret: do not post it in public
  chats or photos.
- Kiosk devices are on the same network. Revoke a lost kiosk token in `/camp`.
- A captive-portal wildcard makes all DNS names point at the camp server. This
  is convenient but can confuse phones; the `camp.local` alias is the friendly
  path.

## Rollback

```bash
sudo DRY_RUN=1 bash server/scripts/disable_pi_ap_nat.sh
sudo bash server/scripts/disable_pi_ap_nat.sh
```

This removes the `# LOCAL_CHAT_AP` block from `/etc/dhcpcd.conf`, the local
dnsmasq file, the sysctl override, NAT rules, and stops `hostapd`.

## Troubleshooting

- **`wlan0` does not support AP mode**: use a Wi-Fi adapter/chipset with AP
  mode, or an external router in bridge/AP mode.
- **Bookworm / NetworkManager**: the base helper uses `dhcpcd`; on Bookworm the
  access point may need manual NetworkManager configuration. This is a known
  limitation of the upstream helper, not of Camp Edition.
- **`dnsmasq` will not start**: port 53 is often taken by `systemd-resolved`.
  Disable its stub listener or configure dnsmasq to bind only to the AP
  interface (the helper already sets `bind-interfaces`).
- **`hostapd` masked**: `sudo systemctl unmask hostapd` (the helper does this).
- **Wrong country/channel**: set `CAMP_AP_COUNTRY` and `CAMP_AP_CHANNEL` to
  values allowed in your jurisdiction.
- **Phone says “no internet”**: expected in offline mode; open the portal URL
  manually. Captive-portal detection is not guaranteed on every phone.
- **Portal does not open by name**: use the IP address; check `dnsmasq` and the
  `address=/#/...` line in `/etc/dnsmasq.d/local-chat-ap.conf`.
