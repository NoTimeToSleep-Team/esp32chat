#pragma once

#include "../common/local_chat_runtime.h"

namespace lc {

inline RuntimeConfig make_service_profile(
    const char* device_id,
    const char* device_type,
    const char* wifi_ssid,
    const char* wifi_password,
    const char* server_base_url,
    const char* ops_session_token) {
    RuntimeConfig config = {
        device_id,
        device_type,
        wifi_ssid,
        wifi_password,
        server_base_url,
        ops_session_token,
        "",
        "",
        "device",
        true,
        false,
        false,
        false,
        false,
        false,
        1500,
        15000,
        45000,
        5000,

        0,
        false,
        false,
        false,
        false,
        false,

        0,
        0,

        "",
        "",
        "",
        "",
        "",
        "",
    };
    return config;
}

inline RuntimeConfig make_client_profile(
    const char* device_id,
    const char* device_type,
    const char* wifi_ssid,
    const char* wifi_password,
    const char* server_base_url,
    const char* login,
    const char* password,
    const char* client_kind,
    bool chat_profile,
    bool blog_profile,
    bool support_profile,
    bool admin_profile) {
    RuntimeConfig config = {
        device_id,
        device_type,
        wifi_ssid,
        wifi_password,
        server_base_url,
        "",
        login,
        password,
        client_kind,
        false,
        true,
        chat_profile,
        blog_profile,
        support_profile,
        admin_profile,
        2500,
        15000,
        45000,
        5000,

        0,
        false,
        false,
        false,
        false,
        false,

        0,
        0,

        "",
        "",
        "",
        "",
        "",
        "",
    };
    return config;
}

}  // namespace lc
