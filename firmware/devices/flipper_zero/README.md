# Flipper Zero

Limited client firmware/app target with capability detection.

Shell/capability-detection MVP implemented in `v0.14.01`.

Limited client MVP implemented in `v0.14.02`.

## Scope

- shell skeleton for Flipper runtime flow;
- Wi-Fi dev board capability detection;
- explicit mode split: `limited_local` vs `network`;
- secure login/session/logout only for network-capable mode.
- limited text-first client flow: login, chat list/history/send, blog list/get.

## Files

- `config.py` - flipper baseline config.
- `models.py` - shell/session/capability models.
- `command_map.py` - allowed shell-level auth/mode/health endpoints.
- `server_api.py` - gateway and sender abstraction.
- `shell.py` - capability detection and shell lifecycle.
- `controller.py` - shell orchestration.
- `verify_mvp.py` - local shell/capability verification against `TestClient`.
- `ui/*` - limited client runtime modules.
- `ui/verify_flow.py` - local limited-client verification against `TestClient`.

## Verification

Run from project root:

```bash
python -m firmware.devices.flipper_zero.verify_mvp
python -m firmware.devices.flipper_zero.ui.verify_flow
```
