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

inline RuntimeConfig make_m5stamp_s3_preset() {
    return make_service_profile(
        "m5stamp-s3-01",
        "m5stamp_s3",
        LC_WIFI_SSID,
        LC_WIFI_PASSWORD,
        LC_SERVER_BASE_URL,
        LC_OPS_SESSION_TOKEN);
}

}  // namespace lc
