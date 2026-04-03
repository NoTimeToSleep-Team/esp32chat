#pragma once

#include <stdbool.h>

typedef enum {
    LocalChatAuthStateIdle = 0,
    LocalChatAuthStateUnavailable = 1,
    LocalChatAuthStateNotImplemented = 2,
} LocalChatAuthState;

typedef struct {
    bool wifi_dev_board_present;
    LocalChatAuthState auth_state;
} LocalChatApi;

void local_chat_api_init(LocalChatApi* api);
bool local_chat_api_wifi_available(const LocalChatApi* api);
void local_chat_api_reset_auth(LocalChatApi* api);
void local_chat_api_request_auth(LocalChatApi* api);
const char* local_chat_api_auth_state_label(LocalChatAuthState state);
