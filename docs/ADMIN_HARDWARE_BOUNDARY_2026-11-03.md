# Admin / hardware boundary (2026-11-03)

## Decision

The web administrator is a **chat administrator**, not a machine administrator.
A browser session with the `admin` role can manage chat users, content, reports,
modes and chat settings, but it cannot inspect or control the host, its services,
network interfaces or attached hardware.

## Web surface

The following web routers are no longer mounted:

- `/ops/*` (system health, service restart, reboot, clock sync, app ops)
- `/admin/network/*` (Wi-Fi, interfaces, hostapd/dnsmasq, iptables-backed access)
- `/admin/api/deployment/*` and `/admin/api/modules/*`
- `/rfid/*`
- `/api/m5tab/*`
- `/devices/api/edge/*`
- device-runtime telemetry endpoints under `/ops/api/devices/*`

In addition, `app/security/infrastructure.py` defines an explicit prefix
boundary. A middleware answers every matching path with a generic `404` before
authentication, even if a router is accidentally mounted again in the future.

The admin HTML no longer contains the `System` or `Network` tabs, the reboot /
service-restart buttons, the system statistics renderer or the login-time
`/ops/api/sync-time` call.

## Host isolation

`local-chat-server.service` now runs with:

- `NoNewPrivileges=yes`
- `PrivateDevices=yes`, `DevicePolicy=closed`
- empty `CapabilityBoundingSet` and `AmbientCapabilities`
- `ProtectSystem=strict`, `ProtectHome=yes`, `ProtectClock=yes`
- `ProtectKernelTunables/Modules/Logs`, `ProtectControlGroups`, `ProtectHostname`
- `RestrictRealtime`, `RestrictSUIDSGID`, `LockPersonality`
- `UnsetEnvironment=LC_SUDO_PASSWORD`
- writable access limited to `/opt/local-chat-server/data`

The old `date` NOPASSWD sudoers rule for `localchat` was removed. The service
process has `NoNewPrivs=1`, zero effective/bounding capabilities and a private
`/dev` without GPIO/I2C/SPI nodes.

## Local operator path

Host actions are available only from a root TTY/SSH session:

```bash
sudo lc-operator status
sudo lc-operator restart-service local-chat-server
sudo lc-operator reboot --confirm
sudo lc-operator shutdown --confirm
```

## Verification

- Admin web boundary: **26/26** (all infrastructure paths `404`, OpenAPI clean,
  chat/admin APIs still work).
- Chat regressions: **38/38** (F8/F9/F10/F11/F12).
- Prior update/private/device regressions: **13/13**.
- Live service: `active`, boot self-test `9/9`, `/health` `200`.
- Process: `CapEff=0`, `CapBnd=0`, `NoNewPrivs=1`, `PrivateDevices=yes`,
  `localchat` sudo denied.

## Residual

An operator with root SSH/console access still controls the device. That is the
intended out-of-band management path and is outside the web application's
trust boundary.
