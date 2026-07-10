# ESP32Chat v0.8.0-alpha — Raspberry Pi server preview

This is the first public engineering alpha of ESP32Chat. It packages the Raspberry Pi server work and early client/runtime components for testing and development.

## Included

- Raspberry Pi 5 and Raspberry Pi Zero 2 W deployment assets.
- FastAPI server foundation and local web interfaces.
- Realtime chat transport and account/chat service components.
- Early native runtime entry points for supported handheld clients.
- Software verification workflow and project documentation.

## Important limitations

- This release is not production-ready.
- Full synchronized testing on all physical devices is incomplete.
- Network-loss, roaming, long-uptime, thermal, and load behavior require more validation.
- Device feature coverage differs by hardware target.
- APIs, configuration, and protocol details may change before a stable release.

Please report reproducible bugs through GitHub Issues and use the hardware validation template for physical-device results. Never publish credentials, Wi-Fi passwords, session tokens, private server addresses, or sensitive logs.
