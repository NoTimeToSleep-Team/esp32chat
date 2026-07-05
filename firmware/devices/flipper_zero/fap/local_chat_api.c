#include "local_chat_api.h"

#include <stddef.h>

#include <furi.h>

#ifndef LOCAL_CHAT_WIFI_DEVBOARD_AVAILABLE
#define LOCAL_CHAT_WIFI_DEVBOARD_AVAILABLE 0
#endif

void local_chat_api_init(LocalChatApi* api) {
    furi_check(api != NULL);
    api->wifi_dev_board_present = (LOCAL_CHAT_WIFI_DEVBOARD_AVAILABLE != 0);
    api->auth_state = LocalChatAuthStateIdle;
}

bool local_chat_api_wifi_available(const LocalChatApi* api) {
    furi_check(api != NULL);
    return api->wifi_dev_board_present;
}

void local_chat_api_reset_auth(LocalChatApi* api) {
    furi_check(api != NULL);
    api->auth_state = LocalChatAuthStateIdle;
}

void local_chat_api_request_auth(LocalChatApi* api) {
    furi_check(api != NULL);
    if(!api->wifi_dev_board_present) {
        api->auth_state = LocalChatAuthStateUnavailable;
        furi_log_w("local_chat_api", "auth blocked: no wifi dev board");
        return;
    }

    api->auth_state = LocalChatAuthStateNotImplemented;
    furi_log_i("local_chat_api", "auth placeholder: network stack not implemented yet");
}

const char* local_chat_api_auth_state_label(LocalChatAuthState state) {
    switch(state) {
    case LocalChatAuthStateIdle:
        return "idle";
    case LocalChatAuthStateUnavailable:
        return "blocked_no_wifi";
    case LocalChatAuthStateNotImplemented:
        return "todo_network_impl";
    default:
        return "unknown";
    }
}
