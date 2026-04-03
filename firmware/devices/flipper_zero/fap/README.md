# Flipper FAP Runtime

This directory contains native C source for Flipper Zero `.fap` build.

Files:

- `application.fam` - external app manifest.
- `local_chat_flipper.c` - basic runtime shell for mode switching and auth placeholder.
- `local_chat_api.h` - native API facade and auth-state model.
- `local_chat_api.c` - capability-aware auth stub (`LOCAL_CHAT_WIFI_DEVBOARD_AVAILABLE`).

Build with official Flipper SDK/FBT from your firmware checkout:

```bash
./fbt fap_local_chat_flipper
```

Optional compile-time flag:

- `LOCAL_CHAT_WIFI_DEVBOARD_AVAILABLE=1` enables network-mode path for UI checks.

The initial runtime keeps realistic constraints:

- no fake full network flow without supported Wi-Fi module;
- lightweight text-first shell behavior;
- explicit `limited_local` and `network` mode indication.
