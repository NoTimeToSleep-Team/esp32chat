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

#ifndef LC_OPS_SESSION_TOKEN
#define LC_OPS_SESSION_TOKEN ""
#endif

namespace lc {

inline RuntimeConfig make_esp32_service_preset() {
    return make_service_profile(
        "esp32-service-01",
        "esp32_service",
        LC_WIFI_SSID,
        LC_WIFI_PASSWORD,
        LC_SERVER_BASE_URL,
        LC_OPS_SESSION_TOKEN);
}

}  // namespace lc
