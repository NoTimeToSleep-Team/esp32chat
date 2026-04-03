#include <stdbool.h>
#include <stdint.h>

#include <furi.h>
#include <gui/gui.h>
#include <input/input.h>

#include "local_chat_api.h"

typedef struct {
    FuriMessageQueue* input_queue;
    bool network_mode;
    LocalChatApi api;
} LocalChatFlipperApp;

static void local_chat_draw_callback(Canvas* canvas, void* ctx) {
    LocalChatFlipperApp* app = ctx;
    canvas_clear(canvas);

    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str(canvas, 2, 10, "Local Chat");

    canvas_set_font(canvas, FontSecondary);
    if(app->network_mode) {
        canvas_draw_str(canvas, 2, 24, "mode: network");
    } else {
        canvas_draw_str(canvas, 2, 24, "mode: limited_local");
    }

    if(local_chat_api_wifi_available(&app->api)) {
        canvas_draw_str(canvas, 2, 36, "wifi dev board: yes");
    } else {
        canvas_draw_str(canvas, 2, 36, "wifi dev board: no");
    }

    canvas_draw_str(canvas, 2, 48, local_chat_api_auth_state_label(app->api.auth_state));
    canvas_draw_str(canvas, 2, 58, "up: mode ok: auth");
    canvas_draw_str(canvas, 2, 68, "down: clear back: exit");
}

static void local_chat_input_callback(InputEvent* input_event, void* ctx) {
    FuriMessageQueue* input_queue = ctx;
    furi_check(furi_message_queue_put(input_queue, input_event, FuriWaitForever) == FuriStatusOk);
}

int32_t local_chat_flipper_app(void* p) {
    UNUSED(p);

    LocalChatFlipperApp app = {0};
    app.input_queue = furi_message_queue_alloc(8, sizeof(InputEvent));
    app.network_mode = false;
    local_chat_api_init(&app.api);

    ViewPort* view_port = view_port_alloc();
    view_port_draw_callback_set(view_port, local_chat_draw_callback, &app);
    view_port_input_callback_set(view_port, local_chat_input_callback, app.input_queue);

    Gui* gui = furi_record_open(RECORD_GUI);
    gui_add_view_port(gui, view_port, GuiLayerFullscreen);

    bool running = true;
    while(running) {
        InputEvent event;
        if(furi_message_queue_get(app.input_queue, &event, 100) != FuriStatusOk) {
            continue;
        }

        if(event.type != InputTypeShort) {
            continue;
        }

        if(event.key == InputKeyBack) {
            running = false;
        } else if(event.key == InputKeyUp) {
            if(local_chat_api_wifi_available(&app.api)) {
                app.network_mode = !app.network_mode;
            } else {
                app.network_mode = false;
                furi_log_w("local_chat_flipper", "network mode blocked: no wifi dev board");
            }
            view_port_update(view_port);
        } else if(event.key == InputKeyDown) {
            local_chat_api_reset_auth(&app.api);
            view_port_update(view_port);
        } else if(event.key == InputKeyOk) {
            local_chat_api_request_auth(&app.api);
            view_port_update(view_port);
        }
    }

    gui_remove_view_port(gui, view_port);
    furi_record_close(RECORD_GUI);
    view_port_free(view_port);
    furi_message_queue_free(app.input_queue);
    return 0;
}
