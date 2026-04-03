# Flipper Zero Capability Notes

This document captures realistic runtime boundaries for Flipper Zero integration.

## Baseline Role

- Flipper Zero is a limited external client.
- Raspberry Pi remains the only main server.
- Guest login is not allowed for Flipper hardware flow.

## Capability Detection

`v0.14.01` introduces shell-level capability detection:

- detect Wi-Fi dev board presence;
- split runtime mode into `limited_local` and `network`;
- block network login path when Wi-Fi dev board is missing.

`v0.14.02` extends this with limited client flow:

- lightweight text login for network-capable mode only;
- chat text send/read and blog read;
- no file/photo upload assumptions.

## Mode Rules

- `limited_local` mode:
  - no server login;
  - no fake claims about full network client features;
  - shell remains in explicit limited state.
- `network` mode:
  - allow health probe and auth/session flow;
  - allow limited text-first chat/blog client flow.

## Honest Constraints

- No promises about full Bluetooth/Wi-Fi/files/photo behavior without real hardware confirmation.
- Hardware flashing and on-device checks are separate from local software verification.
