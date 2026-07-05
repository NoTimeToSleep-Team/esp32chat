#pragma once

#include "runtime_profiles.h"

#ifndef LC_WIFI_SSID
#define LC_WIFI_SSID "YOUR_WIFI_SSID"
#endif

#ifndef LC_WIFI_PASSWORD
#define LC_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

#ifndef LC_SERVER_BASE_URL
#define LC_SERVER_BASE_URL "http://192.168.1.20:18080"
#endif

#ifndef LC_LOGIN
#define LC_LOGIN ""
#endif

#ifndef LC_PASSWORD
#define LC_PASSWORD ""
#endif

#ifndef LC_CHAT_MESSAGE_TEXT
#define LC_CHAT_MESSAGE_TEXT "M5Cardputer console message"
#endif

#ifndef LC_CHAT_SEND_ENABLED
#define LC_CHAT_SEND_ENABLED 0
#endif

#ifndef LC_SUPPORT_CREATE_ENABLED
#define LC_SUPPORT_CREATE_ENABLED 0
#endif

#ifndef LC_PREFERRED_CHAT_ID
#define LC_PREFERRED_CHAT_ID 1
#endif

#ifndef LC_SUPPORT_TITLE
#define LC_SUPPORT_TITLE "M5Cardputer ticket"
#endif

#ifndef LC_SUPPORT_BODY
#define LC_SUPPORT_BODY "Created from native Arduino runtime"
#endif

namespace lc {

inline RuntimeConfig make_m5cardputer_console_preset() {
    RuntimeConfig config = make_client_profile(
        "m5cardputer-console-01",
        "m5cardputer_console",
        LC_WIFI_SSID,
        LC_WIFI_PASSWORD,
        LC_SERVER_BASE_URL,
        LC_LOGIN,
        LC_PASSWORD,
        "device",
        true,
        true,
        true,
        false);

    config.action_interval_ms = 20000;
    config.chat_send_enabled = LC_CHAT_SEND_ENABLED;
    config.support_create_enabled = LC_SUPPORT_CREATE_ENABLED;
    config.preferred_chat_id = LC_PREFERRED_CHAT_ID;

    config.chat_message_text = LC_CHAT_MESSAGE_TEXT;
    config.support_ticket_title = LC_SUPPORT_TITLE;
    config.support_ticket_body = LC_SUPPORT_BODY;
    return config;
}

}  // namespace lc
