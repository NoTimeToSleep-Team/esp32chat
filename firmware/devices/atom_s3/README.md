# Atom S3 Node

Internal status and alert firmware target for Atom S3.

Implemented as MVP in `v0.08.03`.

Native Arduino runtime is available in `atom_s3.ino`.
Preset defaults live in `../../arduino/presets/atom_s3_preset.h`.

## Scope

- status panel state (`ok`/`degraded`/`hold_state`) with compact pattern mapping;
- local alert registry with severity escalation;
- safe quick actions only:
  - maintenance mode on/off (`/ops/api/degraded-mode`),
  - safe shutdown dry-run (`/ops/api/shutdown/dry-run`),
  - network reset request as incident (`/ops/api/incidents`);
- incident publishing and listing for operator visibility;
- strict command map excluding backup operations.

## Files

- `config.py` - runtime config.
- `models.py` - status/alert/quick-action models.
- `alerts.py` - local alert registry.
- `command_map.py` - explicit safe command map.
- `server_api.py` - ops/health gateway.
- `controller.py` - node orchestration.
- `verify_mvp.py` - local end-to-end verification.

## Verification

Run from project root:

```bash
python -m firmware.devices.atom_s3.verify_mvp
```

Python modules in this directory remain as host-side simulation and verification harnesses.
Profile metadata lists harness files under `host_harness_entries`.
