# Camp Wi-Fi access point

Camp Edition does **not** create a Wi-Fi network by itself. The application is a
web server; on-site the access point is provided by the Raspberry Pi (or another
Linux host) with `hostapd` + `dnsmasq`, plus a tiny captive-portal responder.

The default camp profile is:

- **open Wi-Fi** (no password);
- **captive portal**: after connecting, the phone/tablet shows its standard
  "sign in to network" sheet and opens Camp Edition;
- **no internet** (NAT disabled);
- **no manual IP URL** required.

## Target scheme

```
phones / tablets / kiosks
        |  Wi-Fi: CAMP-CHAT (open)
        v
Raspberry Pi 5  wlan0 = 192.168.50.1/24
  hostapd        -> open access point
  dnsmasq        -> DHCP + local DNS (camp.local, chat.local, wildcard)
  captive portal -> port 80: HTTP 302 -> http://192.168.50.1:18080/camp
  FastAPI        -> http://192.168.50.1:18080/camp
        |  (optional) eth0 -> internet only if CAMP_AP_NAT_ENABLED=1
```

The captive portal is a small stdlib Python service
(`server/scripts/camp_captive_portal.py`). It does not proxy or inspect traffic;
it only redirects HTTP requests to the configured camp URL.

## One-command setup

On the Raspberry Pi, from the repository root:

```bash
sudo bash server/scripts/configure_camp_ap.sh
```

Or from `server/`:

```bash
sudo bash ./scripts/configure_camp_ap.sh
```

The wrapper uses `server/scripts/configure_pi_ap_nat.sh` and installs
`camp-captive-portal.service`.

| Setting | Default |
|---|---|
| SSID | `CAMP-CHAT` |
| Wi-Fi security | open (no password) |
| Pi address | `192.168.50.1/24` |
| DHCP range | `192.168.50.50`–`192.168.50.150` |
| Captive portal | port `80`, redirect to `http://192.168.50.1:18080/camp` |
| DNS | all names → `192.168.50.1`; `camp.local` / `chat.local` |
| NAT / internet | off |

### Optional settings

```bash
sudo \
  CAMP_AP_SSID='CAMP-2026' \
  CAMP_AP_COUNTRY='RU' \
  CAMP_AP_CHANNEL=6 \
  CAMP_AP_ADDRESS=192.168.50.1 \
  CAMP_AP_WLAN_IFACE=wlan0 \
  CAMP_PORTAL_PORT=18080 \
  bash server/scripts/configure_camp_ap.sh
```

Use WPA2 instead of an open network:

```bash
sudo \
  CAMP_AP_OPEN=0 \
  CAMP_AP_PASSPHRASE='replace-with-strong-pass' \
  bash server/scripts/configure_camp_ap.sh
```

Disable the captive portal and keep only the AP:

```bash
sudo CAMP_CAPTIVE_PORTAL=0 bash server/scripts/configure_camp_ap.sh
```

With internet uplink (only if the camp policy allows it):

```bash
sudo \
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
systemctl status camp-captive-portal --no-pager
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  -H 'Host: captive.apple.com' http://192.168.50.1/generate_204
```

Expected: `302 http://192.168.50.1:18080/camp`.

Then on a phone:

1. Connect to `CAMP-CHAT`.
2. The OS should show a captive-portal sheet ("Войти в сеть" / "Sign in").
3. Tap it; Camp Edition opens.
4. Log in with a camp web token.

If the sheet does not appear, the fallback is `http://192.168.50.1:18080/camp`
(or `http://camp.local:18080/camp`). The goal is that nobody needs to type it.

## Security

- The default Wi-Fi has **no password**. Anyone in radio range can join the
  network. This is a deliberate usability choice for the camp pilot; treat the
  whole network as untrusted.
- Camp authentication is still required by the web app. Do not put sensitive
  data on a screen unlocked in a public area.
- The captive portal only redirects; it does not capture credentials, proxy
  traffic or inspect HTTPS.
- Firewall the Pi so clients can reach only the portal/API (and DNS/DHCP);
  block SSH and admin ports from the AP interface.
- If the camp policy requires a password, use `CAMP_AP_OPEN=0` with a strong
  WPA2 passphrase.
- Kiosk devices are on the same network. Revoke a lost kiosk token in `/camp`.

## Captive portal details

- `dnsmasq` resolves every name to `192.168.50.1`; `camp.local` and
  `chat.local` are explicit aliases.
- The responder listens on TCP 80 and returns `302` with
  `Location: http://192.168.50.1:18080/camp` for normal requests.
- `/healthz` returns `204` for a simple process check.
- Some clients probe HTTPS; those probes cannot be redirected without a
  certificate, but the standard HTTP probes from iOS/Android/Windows trigger the
  portal sheet. This is the same limitation as the main chat's captive portal.
- The service runs as `nobody` with only `CAP_NET_BIND_SERVICE`; the source
  directory must be readable by that user.

## Rollback

```bash
sudo DRY_RUN=1 bash server/scripts/disable_pi_ap_nat.sh
sudo bash server/scripts/disable_pi_ap_nat.sh
sudo systemctl disable --now camp-captive-portal
```

This removes the `# LOCAL_CHAT_AP` block from `/etc/dhcpcd.conf`, the local
dnsmasq file, the sysctl override, NAT rules, and stops `hostapd` and the
captive portal.

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
- **Portal sheet does not appear**: open the fallback URL once; check
  `systemctl status camp-captive-portal`, `curl` with a forged `Host` header,
  and the `address=/#/...` line in `/etc/dnsmasq.d/local-chat-ap.conf`.
- **Phone says “no internet”**: expected in offline mode; the captive portal
  sheet should still appear. Captive-portal detection is not guaranteed on every
  phone/browser.
