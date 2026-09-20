from __future__ import annotations

import sqlite3
import subprocess
import re
import time

from app.models.internet_access import (
    InternetAccessRecord,
    WiFiInterfaceInfo,
    WiFiInterfaceRole,
    WiFiNetwork,
    WiFiUplinkStatus,
)


class NetworkService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _iptables_rule_exists(self, table: str | None, rule: list[str]) -> bool:
        cmd = ["sudo", "iptables"]
        if table:
            cmd.extend(["-t", table])
        result = subprocess.run(cmd + ["-C"] + rule, capture_output=True, timeout=5)
        return result.returncode == 0

    def _delete_iptables_rule(self, table: str | None, rule: list[str]) -> None:
        cmd = ["sudo", "iptables"]
        if table:
            cmd.extend(["-t", table])
        while self._iptables_rule_exists(table, rule):
            result = subprocess.run(cmd + ["-D"] + rule, capture_output=True, timeout=5)
            if result.returncode != 0:
                break

    def _ensure_iptables_rule(self, table: str | None, rule: list[str]) -> None:
        cmd = ["sudo", "iptables"]
        if table:
            cmd.extend(["-t", table])
        if not self._iptables_rule_exists(table, rule):
            subprocess.run(cmd + ["-A"] + rule, capture_output=True, timeout=5)

    # --- Interface detection & assignment ---

    def detect_interfaces(self) -> list[WiFiInterfaceInfo]:
        interfaces: list[WiFiInterfaceInfo] = []
        try:
            result = subprocess.run(
                ["iw", "dev"],
                capture_output=True, text=True, timeout=10
            )
            current_iface = ""
            current_mac = ""
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Interface "):
                    current_iface = line.split()[1]
                    current_mac = ""
                elif "addr " in line and current_iface:
                    current_mac = line.split()[1]
                    interfaces.append(self._build_iface_info(current_iface, current_mac))
                    current_iface = ""
        except Exception:
            pass

        # fallback: try /sys/class/net for all interfaces (skip virtual/container)
        try:
            import os
            skip_prefixes = ("lo", "docker", "veth", "br-", "virbr")
            for name in sorted(os.listdir("/sys/class/net")):
                if any(name.startswith(p) for p in skip_prefixes):
                    continue
                # Skip already detected wireless interfaces
                if any(i.ifname == name for i in interfaces):
                    continue
                mac = ""
                try:
                    mac_path = f"/sys/class/net/{name}/address"
                    with open(mac_path) as f:
                        mac = f.read().strip()
                except Exception:
                    pass
                interfaces.append(self._build_iface_info(name, mac))
        except Exception:
            pass

        # sort: built-in (wlan0) first, then USB adapters, then modems
        def _sort_key(i: WiFiInterfaceInfo) -> tuple:
            if i.ifname == "wlan0":
                return (0, 0)
            elif i.ifname.startswith("wl"):
                return (0, 1)
            elif i.ifname.startswith("usb") or i.ifname.startswith("ww"):
                return (1, 0)
            elif i.ifname.startswith("eth"):
                return (1, 1)
            return (2, 0)
        interfaces.sort(key=_sort_key)
        return interfaces

    def _build_iface_info(self, ifname: str, mac: str) -> WiFiInterfaceInfo:
        chipset = ""
        tx_power = 20
        try:
            result = subprocess.run(
                ["iw", "phy", f"phy{self._phy_index(ifname)}", "info"] if self._phy_index(ifname) >= 0
                else ["ethtool", "-i", ifname],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "driver:" in line or "chipset" in line.lower():
                    chipset = line.split(":")[-1].strip()
                elif "Available Antennas" in line:
                    pass
        except Exception:
            pass

        # detect role from DB
        role = WiFiInterfaceRole.UNASSIGNED
        priority = 0
        conn = self._connect()
        row = conn.execute("SELECT role, priority FROM wifi_interface_map WHERE ifname = ?", (ifname,)).fetchone()
        if row:
            role = WiFiInterfaceRole(row["role"])
            priority = row["priority"]
        else:
            # auto-assign defaults
            if ifname == "wlan0":
                role = WiFiInterfaceRole.AP
                priority = 10
            elif ifname == "wlan1":
                role = WiFiInterfaceRole.UPLINK
                priority = 5
            self._save_iface_map(ifname, role, priority, chipset, tx_power)
        conn.close()

        return WiFiInterfaceInfo(
            ifname=ifname,
            role=role,
            priority=priority,
            chipset=chipset,
            tx_power_dbm=tx_power,
            mac_address=mac,
        )

    def _phy_index(self, ifname: str) -> int:
        try:
            path = f"/sys/class/net/{ifname}/phy80211/index"
            with open(path) as f:
                return int(f.read().strip())
        except Exception:
            return -1

    def set_interface_role(self, ifname: str, role: WiFiInterfaceRole) -> bool:
        conn = self._connect()
        row = conn.execute("SELECT priority, chipset, tx_power_dbm FROM wifi_interface_map WHERE ifname = ?", (ifname,)).fetchone()
        priority = row["priority"] if row else 0
        chipset = row["chipset"] if row else ""
        tx_power = row["tx_power_dbm"] if row else 20
        conn.close()
        self._save_iface_map(ifname, role, priority, chipset, tx_power)
        self._restart_network_services()
        return True

    def set_interface_roles(self, roles: dict[str, WiFiInterfaceRole]) -> bool:
        """Assign roles for multiple interfaces, then restart network services once."""
        now_ms = int(time.time() * 1000)
        conn = self._connect()
        try:
            for ifname, role in roles.items():
                row = conn.execute("SELECT priority, chipset, tx_power_dbm FROM wifi_interface_map WHERE ifname = ?", (ifname,)).fetchone()
                priority = row["priority"] if row else 0
                chipset = row["chipset"] if row else ""
                tx_power = row["tx_power_dbm"] if row else 20
                conn.execute(
                    """INSERT INTO wifi_interface_map (ifname, role, priority, chipset, tx_power_dbm, assigned_at_ms)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(ifname) DO UPDATE SET role=?, priority=?, chipset=?, tx_power_dbm=?, assigned_at_ms=?""",
                    (ifname, role.value, priority, chipset, tx_power, now_ms,
                     role.value, priority, chipset, tx_power, now_ms),
                )
            conn.commit()
        finally:
            conn.close()
        self._restart_network_services()
        return True

    def set_tx_power(self, ifname: str, power_dbm: int) -> bool:
        power_dbm = min(max(power_dbm, 1), 33)
        try:
            subprocess.run(["sudo", "iwconfig", ifname, "txpower", str(power_dbm)],
                          capture_output=True, timeout=10)
        except Exception:
            pass  # iwconfig may fail on nl80211-only adapters, but try it
        try:
            subprocess.run(["sudo", "iw", "dev", ifname, "set", "txpower", "fixed", str(power_dbm * 100)],
                          capture_output=True, timeout=10)
        except Exception:
            pass  # iw may not be installed
        # Save to DB
        now_ms = int(time.time() * 1000)
        conn = self._connect()
        conn.execute("UPDATE wifi_interface_map SET tx_power_dbm = ?, assigned_at_ms = ? WHERE ifname = ?",
                     (power_dbm, now_ms, ifname))
        conn.commit()
        conn.close()
        return True

    def restart_services(self) -> dict:
        return self._restart_network_services()

    def _restart_network_services(self) -> dict:
        conn = self._connect()
        rows = conn.execute("SELECT ifname FROM wifi_interface_map WHERE role = 'ap' ORDER BY priority DESC").fetchall()
        total_map_rows = int(conn.execute("SELECT COUNT(*) AS n FROM wifi_interface_map").fetchone()["n"])
        conn.close()
        ap_ifaces = [r["ifname"] for r in rows]
        if not ap_ifaces and total_map_rows == 0:
            # No assignments recorded yet: keep the legacy single-AP behaviour.
            ap_ifaces = ["wlan0"]
        if not ap_ifaces:
            try:
                subprocess.run(["sudo", "systemctl", "stop", "hostapd"], capture_output=True, timeout=10)
                subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], capture_output=True, timeout=10)
                self.ensure_uplink_routing()
            except Exception as exc:
                return {"status": "error", "message": str(exc)}
            return {"status": "ok", "ap_interface": None, "message": "No AP interfaces assigned; hostapd/dnsmasq stopped"}
        primary_ap = ap_ifaces[0]
        try:
            # Update hostapd.conf for primary AP
            conf = (f"interface={primary_ap}\n"
                    f"driver=nl80211\n"
                    f"ssid=local-chat\n"
                    f"hw_mode=g\n"
                    f"channel=1\n"
                    f"auth_algs=1\n"
                    f"wmm_enabled=0\n")
            subprocess.run(["sudo", "tee", "/etc/hostapd/hostapd.conf"],
                          input=conf, capture_output=True, text=True, timeout=10)

            # Update dnsmasq.conf — listen on all AP interfaces
            dns_interfaces = "\n".join(f"interface={iface}" for iface in ap_ifaces)
            dns_conf = (f"{dns_interfaces}\n"
                        f"dhcp-range=192.168.4.2,192.168.4.50,255.255.255.0,24h\n"
                        f"dhcp-option=3,192.168.4.1\n"
                        f"dhcp-option=6,192.168.4.1\n"
                        f"address=/#/192.168.4.1\n"
                        f"server=8.8.8.8\n"
                        f"no-hosts\n"
                        f"bind-interfaces\n")
            subprocess.run(["sudo", "tee", "/etc/dnsmasq.conf"],
                          input=dns_conf, capture_output=True, text=True, timeout=10)

            # Restart services
            subprocess.run(["sudo", "systemctl", "restart", "hostapd"], capture_output=True, timeout=10)
            subprocess.run(["sudo", "systemctl", "restart", "dnsmasq"], capture_output=True, timeout=10)
            subprocess.run(["sudo", "systemctl", "restart", "local-chat-proxy"], capture_output=True, timeout=10)

            # Assign IP and bring up all AP interfaces
            for ap_iface in ap_ifaces:
                subprocess.run(["sudo", "ip", "addr", "add", "192.168.4.1/24", "dev", ap_iface],
                              capture_output=True, timeout=5)
                subprocess.run(["sudo", "ip", "link", "set", ap_iface, "up"], capture_output=True, timeout=5)

            # Set up internet routing + iptables for all uplinks
            self.ensure_uplink_routing()
            self._apply_iptables_rules()
            # Persist rules for next boot
            subprocess.run(["sudo", "sh", "-c", "iptables-save > /etc/iptables/rules.v4"],
                          capture_output=True, timeout=10)

            return {"status": "ok", "ap_interface": primary_ap}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_uplink_ifaces(self) -> list[str]:
        conn = self._connect()
        rows = conn.execute("SELECT ifname FROM wifi_interface_map WHERE role = 'uplink' ORDER BY priority DESC").fetchall()
        conn.close()
        ifaces = [r["ifname"] for r in rows]
        return ifaces

    def get_uplink_iface(self) -> str:
        ifaces = self.get_uplink_ifaces()
        return ifaces[0] if ifaces else ""

    def get_ap_ifaces(self) -> list[str]:
        conn = self._connect()
        rows = conn.execute("SELECT ifname FROM wifi_interface_map WHERE role = 'ap' ORDER BY priority DESC").fetchall()
        conn.close()
        ifaces = [r["ifname"] for r in rows]
        return ifaces if ifaces else ["wlan0"]

    def get_ap_iface(self) -> str:
        return self.get_ap_ifaces()[0]

    def _save_iface_map(self, ifname: str, role: WiFiInterfaceRole, priority: int, chipset: str, tx_power: int) -> None:
        now_ms = int(time.time() * 1000)
        conn = self._connect()
        conn.execute(
            """INSERT INTO wifi_interface_map (ifname, role, priority, chipset, tx_power_dbm, assigned_at_ms)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(ifname) DO UPDATE SET role=?, priority=?, chipset=?, tx_power_dbm=?, assigned_at_ms=?""",
            (ifname, role.value, priority, chipset, tx_power, now_ms,
             role.value, priority, chipset, tx_power, now_ms),
        )
        conn.commit()
        conn.close()

    # --- WiFi scan (on selected interface) ---

    def scan_wifi(self, interface: str | None = None) -> list[WiFiNetwork]:
        iface = interface or self.get_uplink_iface()
        if not iface:
            return []
        try:
            result = subprocess.run(
                ["sudo", "iw", "dev", iface, "scan"],
                capture_output=True, text=True, timeout=30
            )
        except Exception:
            return []

        networks: list[WiFiNetwork] = []
        current_ssid = ""
        current_signal = 0
        current_security = "open"

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID:"):
                current_ssid = line[5:].strip()
            elif "signal:" in line:
                sig = re.search(r'signal: -?(\d+)', line)
                if sig:
                    dbm = int(sig.group(1))
                    current_signal = min(max(2 * (dbm + 100), 0), 100)
            elif "RSN:" in line or "WPA:" in line:
                current_security = "wpa"

            if current_ssid and not line:
                networks.append(WiFiNetwork(ssid=current_ssid, signal_strength=current_signal, security=current_security))
                current_ssid = ""
                current_signal = 0
                current_security = "open"

        if current_ssid:
            networks.append(WiFiNetwork(ssid=current_ssid, signal_strength=current_signal, security=current_security))

        seen: set[str] = set()
        unique: list[WiFiNetwork] = []
        for n in sorted(networks, key=lambda n: -n.signal_strength):
            if n.ssid not in seen:
                seen.add(n.ssid)
                unique.append(n)
        return unique

    # --- WiFi connect / disconnect (on uplink interface) ---

    def connect_wifi(self, ssid: str, password: str, interface: str | None = None) -> bool:
        iface = interface or self.get_uplink_iface()
        if not iface:
            return False
        try:
            result = subprocess.run(
                ["sudo", "wpa_cli", "-i", iface, "list_networks"],
                capture_output=True, text=True, timeout=10
            )
            network_id = None
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == ssid:
                    network_id = parts[0]
                    break

            if network_id is None:
                result = subprocess.run(
                    ["sudo", "wpa_cli", "-i", iface, "add_network"],
                    capture_output=True, text=True, timeout=10
                )
                network_id = result.stdout.strip()

            if network_id:
                subprocess.run(["sudo", "wpa_cli", "-i", iface, "set_network", network_id, "ssid", f'"{ssid}"'],
                              capture_output=True, text=True, timeout=10)
                if password:
                    subprocess.run(["sudo", "wpa_cli", "-i", iface, "set_network", network_id, "psk", f'"{password}"'],
                                  capture_output=True, text=True, timeout=10)
                subprocess.run(["sudo", "wpa_cli", "-i", iface, "enable_network", network_id],
                              capture_output=True, text=True, timeout=10)
                subprocess.run(["sudo", "wpa_cli", "-i", iface, "select_network", network_id],
                              capture_output=True, text=True, timeout=10)
                subprocess.run(["sudo", "wpa_cli", "-i", iface, "save_config"],
                              capture_output=True, text=True, timeout=10)

            self._update_uplink_config(ssid, True)
            return True
        except Exception:
            return False

    def disconnect_wifi(self, interface: str | None = None) -> bool:
        iface = interface or self.get_uplink_iface()
        try:
            subprocess.run(["sudo", "wpa_cli", "-i", iface, "disconnect"],
                          capture_output=True, text=True, timeout=10)
            self._update_uplink_config("", False)
            return True
        except Exception:
            return False

    def get_uplink_status(self) -> WiFiUplinkStatus:
        iface = self.get_uplink_iface()
        ip_address = None
        if iface:
            try:
                result = subprocess.run(["ip", "-4", "addr", "show", iface],
                                        capture_output=True, text=True, timeout=10)
                match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                if match:
                    ip_address = match.group(1)
            except Exception:
                pass

        ssid = ""
        connected = False
        conn = self._connect()
        row = conn.execute("SELECT ssid, connected FROM wifi_uplink_config WHERE id = 1").fetchone()
        conn.close()
        if row:
            ssid = row["ssid"]
            connected = bool(row["connected"])

        if ip_address and not connected:
            connected = True
            self._update_uplink_config(ssid, True)

        return WiFiUplinkStatus(ssid=ssid, connected=connected, interface_name=iface, ip_address=ip_address)

    def _update_uplink_config(self, ssid: str, connected: bool) -> None:
        now_ms = int(time.time() * 1000)
        iface = self.get_uplink_iface()
        conn = self._connect()
        conn.execute(
            "UPDATE wifi_uplink_config SET ssid = ?, connected = ?, interface_name = ?, last_connected_at_ms = ?, updated_at_ms = ? WHERE id = 1",
            (ssid, int(connected), iface, now_ms if connected else None, now_ms),
        )
        conn.commit()
        conn.close()

    # --- Internet access per user ---

    def ensure_uplink_routing(self) -> bool:
        iface = self.get_uplink_iface()
        try:
            # Check if interface has IP
            result = subprocess.run(["ip", "-4", "addr", "show", iface], capture_output=True, text=True, timeout=10)
            match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/(\d+)', result.stdout)
            if not match:
                return False
            ip_addr = match.group(1)
            subnet = match.group(2)
            gateway = '.'.join(ip_addr.split('.')[:3]) + '.1'

            # Add subnet route if missing
            subnet_net = f"{ip_addr}/{subnet}"
            subprocess.run(["sudo", "ip", "route", "replace", subnet_net, "dev", iface, "proto", "kernel", "scope", "link", "src", ip_addr],
                          capture_output=True, timeout=5)

            # Add default route via gateway
            subprocess.run(["sudo", "ip", "route", "replace", "default", "via", gateway, "dev", iface, "metric", "200"],
                          capture_output=True, timeout=5)

            # Enable forwarding
            subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], capture_output=True, timeout=5)

            # NAT for AP clients to internet
            ap_iface = self.get_ap_iface()
            subprocess.run(["sudo", "iptables", "-t", "nat", "-C", "POSTROUTING", "-s", "192.168.4.0/24", "-o", iface, "-j", "MASQUERADE"],
                          capture_output=True, timeout=5)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-A", "POSTROUTING", "-s", "192.168.4.0/24", "-o", iface, "-j", "MASQUERADE"],
                          capture_output=True, timeout=5)  # -C checks, -A adds if missing

            # Allow forwarding between AP and uplink
            for rule in [
                ["-i", ap_iface, "-o", iface, "-j", "ACCEPT"],
                ["-i", iface, "-o", ap_iface, "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
            ]:
                subprocess.run(["sudo", "iptables", "-C", "FORWARD"] + rule, capture_output=True, timeout=5)
                subprocess.run(["sudo", "iptables", "-A", "FORWARD"] + rule, capture_output=True, timeout=5)

            # Save iptables
            subprocess.run(["sudo", "sh", "-c", "iptables-save > /etc/iptables/rules.v4 2>/dev/null || iptables-save > /tmp/iptables-backup.v4"],
                          capture_output=True, timeout=10)

            return True
        except Exception:
            return False

    def set_user_internet(self, user_id: int, enabled: bool, admin_user_id: int) -> bool:
        now_ms = int(time.time() * 1000)
        conn = self._connect()
        conn.execute(
            """INSERT INTO internet_access (user_id, enabled, granted_at_ms, granted_by_admin_user_id)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET enabled=?, granted_at_ms=?, granted_by_admin_user_id=?""",
            (user_id, int(enabled), now_ms, admin_user_id, int(enabled), now_ms, admin_user_id),
        )
        conn.commit()
        conn.close()
        self._apply_iptables_rules()
        return True

    def get_user_internet(self, user_id: int) -> InternetAccessRecord:
        conn = self._connect()
        row = conn.execute("SELECT * FROM internet_access WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if row:
            return InternetAccessRecord(
                user_id=row["user_id"], enabled=bool(row["enabled"]),
                bandwidth_limit_kbps=row["bandwidth_limit_kbps"],
                granted_at_ms=row["granted_at_ms"], granted_by_admin_user_id=row["granted_by_admin_user_id"],
            )
        return InternetAccessRecord(user_id=user_id, enabled=False, bandwidth_limit_kbps=None,
                                     granted_at_ms=0, granted_by_admin_user_id=None)

    def get_all_internet_access(self) -> list[InternetAccessRecord]:
        conn = self._connect()
        rows = conn.execute("SELECT * FROM internet_access").fetchall()
        conn.close()
        return [
            InternetAccessRecord(user_id=r["user_id"], enabled=bool(r["enabled"]),
                                  bandwidth_limit_kbps=r["bandwidth_limit_kbps"],
                                  granted_at_ms=r["granted_at_ms"], granted_by_admin_user_id=r["granted_by_admin_user_id"])
            for r in rows
        ]

    def _apply_iptables_rules(self) -> None:
        try:
            AP_IFACES = self.get_ap_ifaces()
            UPLINK_IFACES = self.get_uplink_ifaces()

            # Ensure internet routing is set up
            self.ensure_uplink_routing()

            # Init chains
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F", "LC_INTERNET"],
                          capture_output=True, timeout=10)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F", "LC_PROXY_REDIRECT"],
                          capture_output=True, timeout=10)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-N", "LC_INTERNET"],
                          capture_output=True, timeout=5)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-N", "LC_PROXY_REDIRECT"],
                          capture_output=True, timeout=5)

            # Redirect HTTP/HTTPS from ALL APs to proxy
            for AP_IFACE in AP_IFACES:
                stale_portal_rules = [
                    ["PREROUTING", "-i", AP_IFACE, "-p", "tcp", "--dport", "80", "-j", "DNAT", "--to-destination", "192.168.4.1:80"],
                    ["PREROUTING", "-i", AP_IFACE, "-p", "tcp", "--dport", "80", "-j", "REDIRECT", "--to-port", "80"],
                    ["PREROUTING", "-i", AP_IFACE, "-p", "tcp", "--dport", "80", "-j", "REDIRECT", "--to-port", "18080"],
                ]
                for rule in stale_portal_rules:
                    self._delete_iptables_rule("nat", rule)

                for port in ["80", "443"]:
                    redirect_rule = ["PREROUTING", "-i", AP_IFACE, "-p", "tcp", "--dport", port, "-j", "REDIRECT", "--to-port", "3128"]
                    self._delete_iptables_rule("nat", redirect_rule)
                    self._ensure_iptables_rule("nat", redirect_rule)

            # MASQUERADE + Forward for ALL uplinks
            for UPLINK_IFACE in UPLINK_IFACES:
                masquerade_rule = ["POSTROUTING", "-o", UPLINK_IFACE, "-j", "MASQUERADE"]
                self._delete_iptables_rule("nat", masquerade_rule)
                self._ensure_iptables_rule("nat", masquerade_rule)

                for AP_IFACE in AP_IFACES:
                    forward_out_rule = ["FORWARD", "-i", AP_IFACE, "-o", UPLINK_IFACE, "-j", "ACCEPT"]
                    forward_back_rule = ["FORWARD", "-i", UPLINK_IFACE, "-o", AP_IFACE,
                                         "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"]
                    self._delete_iptables_rule(None, forward_out_rule)
                    self._ensure_iptables_rule(None, forward_out_rule)
                    self._delete_iptables_rule(None, forward_back_rule)
                    self._ensure_iptables_rule(None, forward_back_rule)

            # Save rules
            subprocess.run(["sudo", "sh", "-c", "iptables-save > /etc/iptables/rules.v4 2>/dev/null; iptables-save > /tmp/iptables-backup.v4"],
                          capture_output=True, timeout=10)

            # Enable IP forwarding
            with open("/proc/sys/net/ipv4/ip_forward", "w") as f:
                f.write("1")
        except Exception:
            pass

    # --- Internet health monitor + failover ---

    def check_internet_health(self, iface: str | None = None) -> bool:
        """Test if a specific uplink (or any) has internet via TCP to 8.8.8.8:53."""
        import socket
        ifaces = [iface] if iface else self.get_uplink_ifaces()
        for ifname in ifaces:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect(("8.8.8.8", 53))
                s.close()
                return True
            except Exception:
                continue
        return False

    def get_healthy_uplink(self) -> str | None:
        """Return the first uplink with working internet, or None."""
        for iface in self.get_uplink_ifaces():
            if self.check_internet_health(iface):
                return iface
        return None

    def balance_uplinks(self) -> None:
        """Apply MASQUERADE for all healthy uplinks (load balancing)."""
        ap_ifaces = self.get_ap_ifaces()
        for uplink in self.get_uplink_ifaces():
            if self.check_internet_health(uplink):
                for ap_iface in ap_ifaces:
                    subprocess.run(
                        ["sudo", "iptables", "-t", "nat", "-C", "POSTROUTING",
                         "-s", "192.168.4.0/24", "-o", uplink, "-j", "MASQUERADE"],
                        capture_output=True, timeout=5)
                    subprocess.run(
                        ["sudo", "iptables", "-t", "nat", "-A", "POSTROUTING",
                         "-s", "192.168.4.0/24", "-o", uplink, "-j", "MASQUERADE"],
                        capture_output=True, timeout=5)
                    for rule in [
                        ["-i", ap_iface, "-o", uplink, "-j", "ACCEPT"],
                        ["-i", uplink, "-o", ap_iface, "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
                    ]:
                        subprocess.run(["sudo", "iptables", "-C", "FORWARD"] + rule,
                                       capture_output=True, timeout=5)
                        subprocess.run(["sudo", "iptables", "-A", "FORWARD"] + rule,
                                       capture_output=True, timeout=5)
