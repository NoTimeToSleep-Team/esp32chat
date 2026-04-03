# Known Limitations

This document lists confirmed limits of the current MVP/RC baseline.

Stage reference: `v0.16.02`.

## Hardware Validation Pending

- No full field run on all physical devices in one synchronized scenario.
- Network quality behavior (packet loss/jitter/roaming) is not validated on real deployment topology.
- Continuous power + thermal envelope for long uptime remains hardware-pending.

## Device Capability Limits

- Devices without confirmed storage do not provide deep offline media/file history.
- Flipper Zero full network flow depends on external Wi-Fi dev board availability.
- Compact clients remain text-first; no unverified voice/media pipeline is claimed.

## Operational Limits

- Git repository in `D:\project` is not initialized yet.
- Deployment docs exist, but no claim of production deployment execution is made in this session.
- Backup/incident/shutdown logic is implemented at software level; real operator drills are still required.

## Integration Limits

- Stage-15 e2e checks are software-level (`FastAPI TestClient`) and not a substitute for hardware acceptance.
- Realtime chat parity is validated for schema/flow, not for stressed multi-node load.
- Ops e2e validates minimal mandatory scenarios; broader operational load tests remain pending.

## Security Limits

- Defensive controls are implemented for baseline protection but are not a claim of full hardening.
- No external penetration testing or formal audit is declared in current status.

## Release Gate Implication

RC1 may proceed as an engineering checkpoint if these limits remain explicitly visible in release notes and operator docs.
Field-ready acceptance still requires dedicated hardware and operational validation passes.

Hardware execution artifacts should be tracked via:

- `docs/hardware-validation-checklist.md`
- `docs/hardware-validation-log-template.md`
