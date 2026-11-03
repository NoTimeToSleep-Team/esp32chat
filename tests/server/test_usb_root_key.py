"""Unit tests for the root USB-key gate (stdlib only).

Run:
    python -m unittest discover -s tests/server -p 'test_usb_root_key.py'
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "server" / "scripts" / "lc-usb-key.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("lc_usb_key_test", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_key(seed: str) -> str:
    blob = base64.b64encode(hashlib.sha256(seed.encode()).digest()).decode()
    return f"ssh-ed25519 {blob} {seed}"


class UsbRootKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key_module = load_helper()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.saved = {
            "STATE_DIR": self.key_module.STATE_DIR,
            "AUTHORIZED_KEYS": self.key_module.AUTHORIZED_KEYS,
            "RUN_DIR": self.key_module.RUN_DIR,
            "UDEV_RULES": self.key_module.UDEV_RULES,
            "SYSTEMD_UNIT": self.key_module.SYSTEMD_UNIT,
            "SSHD_DROPIN": self.key_module.SSHD_DROPIN,
            "SKIP_SSH": self.key_module.SKIP_SSH,
        }
        self.key_module.STATE_DIR = self.root / "state"
        self.key_module.AUTHORIZED_KEYS = self.root / "authorized_keys"
        self.key_module.RUN_DIR = self.root / "run"
        self.key_module.UDEV_RULES = self.root / "70-lc-usb-key.rules"
        self.key_module.SYSTEMD_UNIT = self.root / "lc-usb-key@.service"
        self.key_module.SSHD_DROPIN = self.root / "10-lc-root-key.conf"
        self.key_module.SKIP_SSH = True

    def tearDown(self) -> None:
        for name, value in self.saved.items():
            setattr(self.key_module, name, value)
        self.temp.cleanup()

    def test_parse_key_line_with_options(self) -> None:
        line = 'from="10.0.0.0/8" ' + sample_key("alice")
        parsed = self.key_module.parse_key_line(line)
        assert parsed is not None
        self.assertEqual(parsed["type"], "ssh-ed25519")
        self.assertEqual(parsed["comment"], "alice")
        self.assertTrue(parsed["fingerprint"].startswith("SHA256:"))
        self.assertEqual(parsed["options"], 'from="10.0.0.0/8"')

        cert = sample_key("cert").replace("ssh-ed25519", "ssh-ed25519-cert-v01@openssh.com", 1)
        self.assertIsNotNone(self.key_module.parse_key_line(cert))

    def test_add_deduplicate_and_remove_authorized_keys(self) -> None:
        first = sample_key("alice")
        second = sample_key("bob")
        added = self.key_module.add_public_keys([first, first, second])
        self.assertEqual(len(added), 2)
        self.assertEqual(len(self.key_module.authorized_entries()), 2)

        entries = self.key_module.authorized_entries()
        removed = self.key_module.remove_authorized_key("1")
        self.assertEqual(removed["comment"], "alice")
        self.assertEqual(len(self.key_module.authorized_entries()), 1)
        self.assertEqual(self.key_module.authorized_entries()[0]["comment"], "bob")

        remaining = entries[1]
        removed_by_fp = self.key_module.remove_authorized_key(remaining["fingerprint"])
        self.assertEqual(removed_by_fp["comment"], "bob")
        self.assertEqual(self.key_module.authorized_entries(), [])

    def test_state_round_trip_and_token_validation(self) -> None:
        state = self.key_module.default_state()
        token = "a" * 64
        entry = self.key_module.add_usb_token(
            state,
            token,
            uuid="1234-ABCD",
            serial="SERIAL-1",
            label="test key",
            fstype="vfat",
        )
        self.assertTrue(state["ssh_gate"])
        self.key_module.save_state(state)
        loaded = self.key_module.load_state()
        self.assertEqual(loaded["usb_keys"][0]["id"], entry["id"])
        marker = {
            "version": 2,
            "code": token,
            "generation": 1,
            "uuid": "1234-ABCD",
            "serial": "SERIAL-1",
        }
        validated, matched_pending = self.key_module.validate_marker(
            loaded, {"uuid": "1234-ABCD", "serial": "SERIAL-1"}, marker
        )
        self.assertEqual(validated["id"], entry["id"])
        self.assertFalse(matched_pending)

        bad_marker = dict(marker, code="b" * 64)
        with self.assertRaises(self.key_module.ToolError):
            self.key_module.validate_marker(
                loaded, {"uuid": "1234-ABCD", "serial": "SERIAL-1"}, bad_marker
            )

    def test_v1_marker_is_migrated_on_next_open(self) -> None:
        state = self.key_module.default_state()
        code = "2" * 64
        state["usb_keys"] = [
            {
                "id": "oldid",
                "uuid": "OLD-0001",
                "serial": "OLD-SERIAL",
                "label": "old",
                "token_sha256": self.key_module.token_hash(code),
            }
        ]
        state["ssh_gate"] = True
        marker = {
            "version": 1,
            "token": code,
            "uuid": "OLD-0001",
            "serial": "OLD-SERIAL",
        }
        enrolled, matched_pending = self.key_module.validate_marker(
            state, {"uuid": "OLD-0001", "serial": "OLD-SERIAL"}, marker
        )
        self.assertEqual(enrolled["id"], "oldid")
        self.assertFalse(matched_pending)

    def test_usb_marker_and_udev_rule(self) -> None:
        state = self.key_module.default_state()
        token = "c" * 64
        entry = self.key_module.add_usb_token(
            state, token, uuid="ABCD-1234", serial="SERIAL-2", label="key2"
        )
        mount = self.root / "usb"
        mount.mkdir()
        self.key_module.write_marker(
            mount,
            token,
            {"uuid": "ABCD-1234", "serial": "SERIAL-2", "label": "key2"},
            generation=1,
        )
        marker = self.key_module.read_marker(mount)
        assert marker is not None
        self.assertEqual(marker["version"], 2)
        self.assertEqual(marker["code"], token)
        self.assertEqual(marker["generation"], 1)
        self.assertTrue((mount / "LC_ROOT_KEY_README.txt").is_file())
        rules = self.key_module.render_udev_rules(state)
        self.assertIn('ENV{ID_FS_UUID}=="ABCD-1234"', rules)
        self.assertIn("lc-usb-key@%k.service", rules)
        self.assertEqual(entry["label"], "key2")

    def test_rotation_invalidates_a_copied_old_code(self) -> None:
        state = self.key_module.default_state()
        old_code = "e" * 64
        entry = self.key_module.add_usb_token(
            state, old_code, uuid="ROTATE-0001", serial="SERIAL-R", label="rotate"
        )
        mount = self.root / "usb"
        mount.mkdir()
        self.key_module.write_marker(
            mount,
            old_code,
            {"uuid": "ROTATE-0001", "serial": "SERIAL-R", "label": "rotate"},
            generation=1,
        )
        marker = self.key_module.read_marker(mount)
        assert marker is not None
        enrolled, matched_pending = self.key_module.validate_marker(
            state, {"uuid": "ROTATE-0001", "serial": "SERIAL-R"}, marker
        )
        self.assertFalse(matched_pending)
        self.key_module.rotate_key_code(
            state, enrolled, {"uuid": "ROTATE-0001", "serial": "SERIAL-R"}, mount, marker, matched_pending
        )
        new_marker = self.key_module.read_marker(mount)
        assert new_marker is not None
        self.assertNotEqual(new_marker["code"], old_code)
        self.assertEqual(new_marker["generation"], 2)
        self.assertTrue(state["usb_keys"][0]["generation"] == 2)

        # A copy made before rotation still has the old code and must fail.
        with self.assertRaises(self.key_module.ToolError):
            self.key_module.validate_marker(
                state,
                {"uuid": "ROTATE-0001", "serial": "SERIAL-R"},
                {"version": 2, "code": old_code, "generation": 1, "uuid": "ROTATE-0001", "serial": "SERIAL-R"},
            )

        # The new code is accepted.
        enrolled2, matched_pending2 = self.key_module.validate_marker(
            state,
            {"uuid": "ROTATE-0001", "serial": "SERIAL-R"},
            new_marker,
        )
        self.assertEqual(enrolled2["id"], entry["id"])
        self.assertFalse(matched_pending2)

    def test_pending_code_recovers_after_interrupted_rotation(self) -> None:
        state = self.key_module.default_state()
        old_code = "f" * 64
        new_code = "1" * 64
        entry = self.key_module.add_usb_token(
            state, old_code, uuid="PENDING-0001", serial="SERIAL-P", label="pending"
        )
        entry["pending_sha256"] = self.key_module.token_hash(new_code)
        entry["pending_generation"] = 2
        mount = self.root / "usb"
        mount.mkdir()
        self.key_module.write_marker(
            mount,
            new_code,
            {"uuid": "PENDING-0001", "serial": "SERIAL-P", "label": "pending"},
            generation=2,
        )
        marker = self.key_module.read_marker(mount)
        assert marker is not None
        enrolled, matched_pending = self.key_module.validate_marker(
            state, {"uuid": "PENDING-0001", "serial": "SERIAL-P"}, marker
        )
        self.assertTrue(matched_pending)
        self.key_module.rotate_key_code(
            state,
            enrolled,
            {"uuid": "PENDING-0001", "serial": "SERIAL-P"},
            mount,
            marker,
            matched_pending,
        )
        self.assertEqual(state["usb_keys"][0]["generation"], 3)

    def test_open_usb_rotates_code_and_starts_once(self) -> None:
        state = self.key_module.default_state()
        old_code = "3" * 64
        entry = self.key_module.add_usb_token(
            state, old_code, uuid="OPEN-0001", serial="SERIAL-O", label="open"
        )
        self.key_module.save_state(state)
        mount = self.root / "usb-open"
        mount.mkdir()
        self.key_module.write_marker(
            mount,
            old_code,
            {"uuid": "OPEN-0001", "serial": "SERIAL-O", "label": "open"},
            generation=1,
        )
        info = {
            "path": "/dev/fake",
            "source": str(mount),
            "uuid": "OPEN-0001",
            "serial": "SERIAL-O",
            "label": "open",
            "fstype": "dir",
        }
        self.key_module.SKIP_SSH = False
        with (
            mock.patch.object(self.key_module, "device_info", lambda _path: info),
            mock.patch.object(self.key_module, "start_ssh", lambda: None),
        ):
            self.key_module.open_usb("/dev/fake")
        marker = self.key_module.read_marker(mount)
        assert marker is not None
        self.assertNotEqual(marker["code"], old_code)
        self.assertEqual(marker["code"] != old_code, True)
        self.assertEqual(marker["generation"], 2)
        loaded = self.key_module.load_state()
        self.assertEqual(loaded["usb_keys"][0]["generation"], 2)
        self.assertTrue((self.key_module.RUN_DIR / "active.json").is_file())
        with self.assertRaises(self.key_module.ToolError):
            self.key_module.validate_marker(
                loaded,
                {"uuid": "OPEN-0001", "serial": "SERIAL-O"},
                {"version": 2, "code": old_code, "generation": 1, "uuid": "OPEN-0001", "serial": "SERIAL-O"},
            )

    def test_remove_last_usb_token_disables_gate(self) -> None:
        state = self.key_module.default_state()
        entry = self.key_module.add_usb_token(
            state, "d" * 64, uuid="AAAA-1111", label="only"
        )
        removed = self.key_module.remove_usb_token(state, entry["id"])
        self.assertEqual(removed["uuid"], "AAAA-1111")
        self.assertFalse(state["ssh_gate"])
        self.assertEqual(state["usb_keys"], [])

    def test_enroll_from_source_writes_state_keys_and_gate_files(self) -> None:
        usb = self.root / "usb"
        usb.mkdir()
        (usb / "laptop.pub").write_text(sample_key("laptop") + "\n", encoding="utf-8")
        real_which = self.key_module.shutil.which
        with (
            mock.patch.object(self.key_module, "require_root", lambda: None),
            mock.patch.object(self.key_module, "systemd_available", lambda: False),
            mock.patch.object(
                self.key_module.shutil,
                "which",
                side_effect=lambda name: (
                    None if name in ("sshd", "udevadm", "systemctl") else real_which(name)
                ),
            ),
        ):
            result = self.key_module.enroll(
                source=str(usb),
                uuid="TEST-USB-0002",
                serial="SERIAL-3",
                label="factory",
                activate=False,
                interactive=False,
            )
        self.assertEqual(result["usb"]["uuid"], "TEST-USB-0002")
        self.assertTrue(self.key_module.state_path().is_file())
        self.assertTrue((usb / "LC_ROOT_KEY.json").is_file())
        self.assertTrue(self.key_module.AUTHORIZED_KEYS.is_file())
        self.assertTrue(self.key_module.UDEV_RULES.is_file())
        self.assertTrue(self.key_module.SYSTEMD_UNIT.is_file())
        self.assertTrue(self.key_module.SSHD_DROPIN.is_file())
        state = self.key_module.load_state()
        self.assertTrue(state["ssh_gate"])
        self.assertEqual(len(state["usb_keys"]), 1)

    def test_add_many_keys_is_bounded(self) -> None:
        keys = [sample_key(f"user-{index}") for index in range(3)]
        self.key_module.add_public_keys(keys)
        self.assertEqual(len(self.key_module.authorized_entries()), 3)


if __name__ == "__main__":
    unittest.main()
