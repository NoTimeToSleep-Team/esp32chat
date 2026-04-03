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

#ifndef LC_ADMIN_REPLY_ENABLED
#define LC_ADMIN_REPLY_ENABLED 0
#endif

#ifndef LC_ADMIN_RESOLVE_ENABLED
#define LC_ADMIN_RESOLVE_ENABLED 0
#endif

#ifndef LC_ADMIN_BLOG_PUBLISH_ENABLED
#define LC_ADMIN_BLOG_PUBLISH_ENABLED 0
#endif

#ifndef LC_ADMIN_TICKET_ID
#define LC_ADMIN_TICKET_ID 0
#endif

#ifndef LC_ADMIN_REPLY_TEXT
#define LC_ADMIN_REPLY_TEXT "M5Tab admin reply from Arduino runtime"
#endif

#ifndef LC_ADMIN_BLOG_TITLE
#define LC_ADMIN_BLOG_TITLE "M5Tab admin post"
#endif

#ifndef LC_ADMIN_BLOG_BODY
#define LC_ADMIN_BLOG_BODY "Published from native Arduino runtime"
#endif

namespace lc {

inline RuntimeConfig make_m5tab_preset() {
    RuntimeConfig config = make_client_profile(
        "m5tab-01",
        "m5tab",
        LC_WIFI_SSID,
        LC_WIFI_PASSWORD,
        LC_SERVER_BASE_URL,
        LC_LOGIN,
        LC_PASSWORD,
        "web",
        false,
        false,
        false,
        true);

    config.action_interval_ms = 30000;
    config.admin_reply_enabled = LC_ADMIN_REPLY_ENABLED;
    config.admin_resolve_enabled = LC_ADMIN_RESOLVE_ENABLED;
    config.admin_blog_publish_enabled = LC_ADMIN_BLOG_PUBLISH_ENABLED;
    config.preferred_ticket_id = LC_ADMIN_TICKET_ID;

    config.admin_reply_text = LC_ADMIN_REPLY_TEXT;
    config.admin_blog_title = LC_ADMIN_BLOG_TITLE;
    config.admin_blog_body = LC_ADMIN_BLOG_BODY;
    return config;
}

}  // namespace lc
