# Raspberry Pi AP + NAT Setup

This guide configures Raspberry Pi as the main Wi-Fi AP and internet gateway for local clients.

Use this only on the target Raspberry Pi (Pi OS) and only with admin access.

## What This Changes

- installs `hostapd`, `dnsmasq`, `iptables-persistent`;
- sets static IP on `wlan0` (default `10.42.0.1/24`);
- enables DHCP on AP subnet;
- enables IPv4 forwarding;
- adds NAT from AP interface (`wlan0`) to uplink (`eth0` by default).

## Safety First

- Run dry-run first.
- Keep a direct Pi console/keyboard access path before applying network changes.
- Do not run on non-Pi hosts.

## Configure AP + NAT

From `server/` directory on Raspberry Pi:

```bash
sudo AP_PASSPHRASE='replace-with-strong-pass' DRY_RUN=1 bash ./scripts/configure_pi_ap_nat.sh
sudo AP_PASSPHRASE='replace-with-strong-pass' bash ./scripts/configure_pi_ap_nat.sh
```

Optional parameters:

```bash
sudo \
  AP_WLAN_IFACE=wlan0 \
  AP_UPLINK_IFACE=eth0 \
  AP_SSID='LocalChatPi' \
  AP_COUNTRY='US' \
  AP_CHANNEL=6 \
  AP_ADDRESS=10.42.0.1 \
  AP_DHCP_START=10.42.0.50 \
  AP_DHCP_END=10.42.0.150 \
  AP_PASSPHRASE='replace-with-strong-pass' \
  bash ./scripts/configure_pi_ap_nat.sh
```

## Verify

```bash
ip addr show wlan0
systemctl status hostapd --no-pager
systemctl status dnsmasq --no-pager
sysctl net.ipv4.ip_forward
iptables -t nat -S POSTROUTING
```

Then connect a client to AP SSID and verify:

- client gets IP from AP subnet;
- client can open server portal/APIs;
- client can access internet through Pi uplink.

## Roll Back

```bash
sudo DRY_RUN=1 bash ./scripts/disable_pi_ap_nat.sh
sudo bash ./scripts/disable_pi_ap_nat.sh
```

Rollback script:

- removes Local Chat AP block from `/etc/dhcpcd.conf`;
- removes local dnsmasq AP config;
- removes local sysctl forwarding override;
- removes NAT/FORWARD rules created by setup script;
- restarts `dhcpcd` and `dnsmasq`, and stops `hostapd`.
