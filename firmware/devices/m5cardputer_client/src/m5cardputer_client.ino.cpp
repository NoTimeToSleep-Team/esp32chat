#include <Arduino.h>
/*
 * M5Cardputer external client firmware (standalone single-file sketch).
 *
 * Fill required macros below, compile in Arduino IDE for ESP32, then flash.
 *
 * This sketch performs:
 * - Wi-Fi connection
 * - /health probe
 * - /auth/login to get user session token
 * - chat/blog/support read probes
 * - optional chat send + support ticket create
 * - Standalone preset equivalent of firmware/arduino/presets/m5cardputer_client_preset.h
 */
#include <HTTPClient.h>
#include <WiFi.h>

#if __has_include(<M5Unified.h>)
#include <M5Unified.h>
#else
#error "M5Unified is required for M5Cardputer sketches; install M5Unified and select the Cardputer board profile."
#endif

#include <string.h>

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

#ifndef LC_CLIENT_KIND
#define LC_CLIENT_KIND "device"
#endif

#ifndef LC_DEVICE_ID
#define LC_DEVICE_ID "m5cardputer-client-01"
#endif

#ifndef LC_DEVICE_TYPE
#define LC_DEVICE_TYPE "m5cardputer_client"
#endif

#ifndef LC_LOOP_DELAY_MS
#define LC_LOOP_DELAY_MS 25
#endif

#ifndef LC_LOOP_INTERVAL_MS
#define LC_LOOP_INTERVAL_MS 1500
#endif

#ifndef LC_ACTION_INTERVAL_MS
#define LC_ACTION_INTERVAL_MS 20000
#endif

#ifndef LC_HTTP_TIMEOUT_MS
#define LC_HTTP_TIMEOUT_MS 5000
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

#ifndef LC_CHAT_MESSAGE_TEXT
#define LC_CHAT_MESSAGE_TEXT "M5Cardputer client message"
#endif

#ifndef LC_SUPPORT_TITLE
#define LC_SUPPORT_TITLE "M5Cardputer client ticket"
#endif

#ifndef LC_SUPPORT_BODY
#define LC_SUPPORT_BODY "Created from native Arduino runtime"
#endif

namespace ui {

struct UiState {
    bool initialized;
    bool wifi_connected;
    bool session_ready;
    bool config_error;
    String config_error_msg;
    String phase;
    String device_id;
    String last_label;
    String last_action;
    int last_code;
    bool last_ok;
    int active_chat_id;
    int active_ticket_id;
    int ok_count;
    int fail_count;
    unsigned long last_draw_ms;
};

UiState g_state = {
    false, false, false, false, "", "boot", "", "", "", -1, false, 0, 0, 0, 0, 0,
};

void draw_line(int y, const String& text, uint16_t color = 0xFFFF) {
    M5.Display.setCursor(6, y);
    M5.Display.setTextColor(color, 0x0000);
    M5.Display.print(text);
}

void render() {
    M5.Display.fillScreen(0x0000);
    M5.Display.fillRect(0, 0, M5.Display.width(), 18, 0x0294);
    M5.Display.setTextColor(0xFFFF, 0x0294);
    M5.Display.setCursor(4, 5);
    M5.Display.print("Cardputer Client");

    draw_line(24, String("phase: ") + g_state.phase, 0xFFFF);
    draw_line(40, String("wifi: ") + (g_state.wifi_connected ? "ok" : "down"), g_state.wifi_connected ? 0x07E0 : 0xF800);
    draw_line(56, String("auth: ") + (g_state.session_ready ? "ok" : "wait"), g_state.session_ready ? 0x07E0 : 0xFBE0);
    draw_line(72, String("chat: ") + String(g_state.active_chat_id) + "  ticket: " + String(g_state.active_ticket_id), 0xFFE0);
    draw_line(88, String("ok=") + String(g_state.ok_count) + " fail=" + String(g_state.fail_count), 0x9FF3);
    draw_line(104, String("last: ") + g_state.last_label + " [" + String(g_state.last_code) + "]", 0xFFFF);
    draw_line(120, String("action: ") + g_state.last_action, 0xBDF7);

    if(g_state.config_error) {
        draw_line(136, String("CONFIG ERROR: ") + g_state.config_error_msg, 0xF800);
    }
}

void begin(const char* device_id) {
    g_state.initialized = true;
    g_state.device_id = String(device_id == nullptr ? "cardputer-client" : device_id);
    auto cfg = M5.config();
    M5.begin(cfg);
    M5.Display.setBrightness(255);
    M5.Display.setRotation(1);
    M5.Display.setTextSize(1);
    g_state.last_draw_ms = 0;
    render();
}

void set_phase(const char* phase) {
    g_state.phase = String(phase == nullptr ? "run" : phase);
}

void set_wifi(bool connected) {
    g_state.wifi_connected = connected;
}

void set_session(bool ready) {
    g_state.session_ready = ready;
}

void set_active_chat(int chat_id) {
    if(chat_id > 0) {
        g_state.active_chat_id = chat_id;
    }
}

void set_active_ticket(int ticket_id) {
    if(ticket_id > 0) {
        g_state.active_ticket_id = ticket_id;
    }
}

void set_config_error(const char* message) {
    g_state.config_error = true;
    g_state.config_error_msg = String(message == nullptr ? "invalid config" : message);
    g_state.phase = "config error";
}

void clear_config_error() {
    g_state.config_error = false;
    g_state.config_error_msg = "";
}

void on_http_result(const char* label, int code, bool ok) {
    g_state.last_label = String(label == nullptr ? "http" : label);
    g_state.last_code = code;
    g_state.last_ok = ok;
    if(ok) {
        g_state.ok_count++;
    } else {
        g_state.fail_count++;
    }
}

void on_action(const char* action_name, bool ok) {
    g_state.last_action = String(action_name == nullptr ? "action" : action_name);
    g_state.phase = ok ? "action ok" : "action fail";
}

void tick() {
    if(!g_state.initialized) {
        return;
    }
    M5.update();
    const unsigned long now_ms = millis();
    if(now_ms - g_state.last_draw_ms >= 300) {
        render();
        g_state.last_draw_ms = now_ms;
    }
}

}  // namespace ui

namespace lc {

struct RuntimeConfig {
    const char* device_id;
    const char* device_type;
    const char* wifi_ssid;
    const char* wifi_password;
    const char* server_base_url;
    const char* login;
    const char* password;
    const char* client_kind;
    unsigned long loop_interval_ms;
    unsigned long action_interval_ms;
    int http_timeout_ms;
    bool chat_profile;
    bool blog_profile;
    bool support_profile;
    bool chat_send_enabled;
    bool support_create_enabled;
    int preferred_chat_id;
    const char* chat_message_text;
    const char* support_ticket_title;
    const char* support_ticket_body;
};

struct HttpResult {
    int status_code;
    bool transport_ok;
    String body;
};

String json_escape(const String& value) {
    String out;
    out.reserve(value.length() + 8);
    for(size_t i = 0; i < value.length(); i++) {
        const char ch = value[i];
        switch(ch) {
        case '\\':
            out += "\\\\";
            break;
        case '"':
            out += "\\\"";
            break;
        case '\n':
            out += "\\n";
            break;
        case '\r':
            out += "\\r";
            break;
        case '\t':
            out += "\\t";
            break;
        default:
            out += ch;
            break;
        }
    }
    return out;
}

String trim_base_url(const char* input) {
    String out = String(input == nullptr ? "" : input);
    while(out.length() > 0 && out.endsWith("/")) {
        out.remove(out.length() - 1);
    }
    return out;
}

String build_url(const char* base_url, const String& path) {
    const String base = trim_base_url(base_url);
    if(path.startsWith("/")) {
        return base + path;
    }
    return base + "/" + path;
}

String json_find_string(const String& body, const char* key) {
    const String marker = String("\"") + key + "\":\"";
    const int marker_index = body.indexOf(marker);
    if(marker_index < 0) {
        return "";
    }

    int cursor = marker_index + marker.length();
    int end = cursor;
    while(end < body.length()) {
        const char ch = body[end];
        if(ch == '\\') {
            end += 2;
            continue;
        }
        if(ch == '"') {
            break;
        }
        end++;
    }

    if(end > body.length()) {
        return "";
    }
    return body.substring(cursor, end);
}

int json_find_int(const String& body, const char* key, int fallback = 0) {
    const String marker = String("\"") + key + "\":";
    const int marker_index = body.indexOf(marker);
    if(marker_index < 0) {
        return fallback;
    }

    int cursor = marker_index + marker.length();
    while(cursor < body.length()) {
        const char ch = body[cursor];
        if(ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n' || ch == '"') {
            cursor++;
            continue;
        }
        break;
    }

    bool negative = false;
    if(cursor < body.length() && body[cursor] == '-') {
        negative = true;
        cursor++;
    }

    long parsed = 0;
    bool has_digit = false;
    while(cursor < body.length()) {
        const char ch = body[cursor];
        if(ch < '0' || ch > '9') {
            break;
        }
        parsed = parsed * 10 + (ch - '0');
        has_digit = true;
        cursor++;
    }

    if(!has_digit) {
        return fallback;
    }

    if(negative) {
        parsed = -parsed;
    }
    return static_cast<int>(parsed);
}

class DeviceRuntime {
public:
    explicit DeviceRuntime(const RuntimeConfig& config)
        : config_(config),
          last_loop_ms_(0),
          last_action_ms_(0),
          active_chat_id_(0),
          active_post_id_(0),
          active_ticket_id_(0),
          chat_send_done_(false),
          chat_history_done_(false),
          blog_post_open_done_(false),
          support_create_done_(false),
          support_messages_done_(false) {
    }

    void begin() {
        ui::set_phase("boot");
        Serial.println("m5cardputer client runtime: boot");
        Serial.print("device_id=");
        Serial.println(config_.device_id);
        Serial.print("device_type=");
        Serial.println(config_.device_type);

        connect_wifi_blocking(15000);
        probe_health();
        ensure_session();
        run_client_probes();
    }

    void loop() {
        const unsigned long now_ms = millis();
        if(now_ms - last_loop_ms_ < config_.loop_interval_ms) {
            return;
        }
        last_loop_ms_ = now_ms;

        if(WiFi.status() != WL_CONNECTED) {
            connect_wifi_blocking(10000);
            return;
        }

        ensure_session();
        run_client_probes();

        const unsigned long action_interval =
            (config_.action_interval_ms > 0) ? config_.action_interval_ms : 15000;
        if(now_ms - last_action_ms_ >= action_interval) {
            run_client_actions();
            last_action_ms_ = now_ms;
        }
    }

private:
    RuntimeConfig config_;
    unsigned long last_loop_ms_;
    unsigned long last_action_ms_;
    int active_chat_id_;
    int active_post_id_;
    int active_ticket_id_;
    bool chat_send_done_;
    bool chat_history_done_;
    bool blog_post_open_done_;
    bool support_create_done_;
    bool support_messages_done_;
    String session_token_;

    bool connect_wifi_blocking(unsigned long timeout_ms) {
        if(config_.wifi_ssid == nullptr || strlen(config_.wifi_ssid) == 0) {
            Serial.println("wifi ssid not configured");
            ui::set_wifi(false);
            ui::set_phase("wifi missing");
            return false;
        }
        if(WiFi.status() == WL_CONNECTED) {
            ui::set_wifi(true);
            return true;
        }

        ui::set_phase("wifi connect");
        Serial.println("wifi connect start");
        WiFi.mode(WIFI_STA);
        WiFi.begin(config_.wifi_ssid, config_.wifi_password == nullptr ? "" : config_.wifi_password);

        const unsigned long started = millis();
        while(WiFi.status() != WL_CONNECTED && (millis() - started) < timeout_ms) {
            delay(250);
        }

        const bool connected = WiFi.status() == WL_CONNECTED;
        if(connected) {
            Serial.print("wifi connected ip=");
            Serial.println(WiFi.localIP());
            ui::set_wifi(true);
            ui::set_phase("wifi connected");
        } else {
            Serial.println("wifi connect timeout");
            ui::set_wifi(false);
            ui::set_phase("wifi timeout");
        }
        return connected;
    }

    HttpResult request_json(const char* method, const String& path, const String& payload = "") {
        HttpResult result;
        result.status_code = -1;
        result.transport_ok = false;

        if(config_.server_base_url == nullptr || strlen(config_.server_base_url) == 0) {
            Serial.println("server base url not configured");
            return result;
        }

        WiFiClient client;
        HTTPClient http;
        const String url = build_url(config_.server_base_url, path);
        if(!http.begin(client, url)) {
            Serial.print("http begin failed url=");
            Serial.println(url);
            return result;
        }

        http.setTimeout(config_.http_timeout_ms);
        int status_code = -1;

        if(strcmp(method, "GET") == 0) {
            status_code = http.GET();
        } else if(strcmp(method, "POST") == 0) {
            http.addHeader("Content-Type", "application/json");
            status_code = http.POST((uint8_t*)payload.c_str(), payload.length());
        } else {
            Serial.print("unsupported method=");
            Serial.println(method);
        }

        result.status_code = status_code;
        result.transport_ok = status_code > 0;
        if(result.transport_ok) {
            result.body = http.getString();
        }

        http.end();
        return result;
    }

    void print_result(const char* label, const HttpResult& result) {
        Serial.print(label);
        Serial.print(" status=");
        Serial.print(result.status_code);
        Serial.print(" ok=");
        Serial.println(result.transport_ok ? "true" : "false");
        ui::on_http_result(label, result.status_code, result.transport_ok);
    }

    void probe_health() {
        const HttpResult result = request_json("GET", "/health");
        print_result("health", result);
    }

    bool ensure_session() {
        if(session_token_.length() > 0) {
            return true;
        }
        if(config_.login == nullptr || strlen(config_.login) == 0 || config_.password == nullptr ||
           strlen(config_.password) == 0) {
            return false;
        }

        const char* client_kind = (config_.client_kind == nullptr || strlen(config_.client_kind) == 0)
                                      ? "device"
                                      : config_.client_kind;
        const String payload = String("{\"login\":\"") + json_escape(String(config_.login)) +
                               "\",\"password\":\"" + json_escape(String(config_.password)) +
                               "\",\"client_kind\":\"" + json_escape(String(client_kind)) + "\"}";

        const HttpResult result = request_json("POST", "/auth/login", payload);
        print_result("auth_login", result);

        if(result.transport_ok && result.status_code == 200) {
            const String token = json_find_string(result.body, "token");
            if(token.length() > 0) {
                session_token_ = token;
                Serial.println("auth token acquired");
                ui::set_session(true);
                ui::set_phase("auth ready");
                return true;
            }
        }
        ui::set_session(false);
        return false;
    }

    void run_client_probes() {
        if(session_token_.length() == 0) {
            return;
        }

        if(config_.chat_profile) {
            const String path = String("/chat/api/chats?session_token=") + session_token_;
            const HttpResult result = request_json("GET", path);
            print_result("chat_list", result);
            const int parsed_chat_id = json_find_int(result.body, "chat_id", 0);
            if(active_chat_id_ <= 0 && parsed_chat_id > 0) {
                active_chat_id_ = parsed_chat_id;
            }
            ui::set_active_chat(resolve_chat_id());
        }

        if(config_.blog_profile) {
            const String path = String("/blog/api/posts?session_token=") + session_token_ + "&limit=5&offset=0";
            const HttpResult result = request_json("GET", path);
            print_result("blog_list", result);
            const int parsed_post_id = json_find_int(result.body, "post_id", 0);
            if(active_post_id_ <= 0 && parsed_post_id > 0) {
                active_post_id_ = parsed_post_id;
            }
        }

        if(config_.support_profile) {
            const String path =
                String("/support/api/tickets?session_token=") + session_token_ + "&limit=5&offset=0";
            const HttpResult result = request_json("GET", path);
            print_result("support_list", result);
            const int parsed_ticket_id = json_find_int(result.body, "ticket_id", 0);
            if(active_ticket_id_ <= 0 && parsed_ticket_id > 0) {
                active_ticket_id_ = parsed_ticket_id;
            }
            ui::set_active_ticket(resolve_ticket_id());
        }
    }

    int resolve_chat_id() const {
        if(config_.preferred_chat_id > 0) {
            return config_.preferred_chat_id;
        }
        return active_chat_id_;
    }

    int resolve_ticket_id() const {
        return active_ticket_id_;
    }

    const char* value_or_default(const char* input, const char* fallback) {
        if(input == nullptr || strlen(input) == 0) {
            return fallback;
        }
        return input;
    }

    void run_client_actions() {
        if(session_token_.length() == 0) {
            return;
        }

        maybe_send_chat_message();
        maybe_probe_chat_history();
        maybe_open_blog_post();
        maybe_create_support_ticket();
        maybe_probe_support_messages();
    }

    void maybe_send_chat_message() {
        if(!config_.chat_send_enabled || chat_send_done_) {
            return;
        }
        const int chat_id = resolve_chat_id();
        if(chat_id <= 0) {
            return;
        }

        const char* message_text = value_or_default(config_.chat_message_text, "hello from m5cardputer client");
        const String payload = String("{\"session_token\":\"") + json_escape(session_token_) +
                               "\",\"body_text\":\"" + json_escape(String(message_text)) +
                               "\",\"client_message_id\":\"m5client-" + String(millis()) + "\"}";
        const String path = String("/chat/api/chats/") + String(chat_id) + "/messages";
        const HttpResult result = request_json("POST", path, payload);
        print_result("chat_send", result);
        ui::on_action("chat send", result.transport_ok && result.status_code == 200);
        if(result.transport_ok && result.status_code == 200) {
            chat_send_done_ = true;
        }
    }

    void maybe_probe_chat_history() {
        if(!config_.chat_profile || chat_history_done_) {
            return;
        }

        const int chat_id = resolve_chat_id();
        if(chat_id <= 0) {
            return;
        }

        const String path = String("/chat/api/chats/") + String(chat_id) +
                           "/messages?session_token=" + session_token_ + "&limit=10&offset=0";
        const HttpResult result = request_json("GET", path);
        print_result("chat_history", result);
        if(result.transport_ok && result.status_code == 200) {
            chat_history_done_ = true;
        }
    }

    void maybe_open_blog_post() {
        if(!config_.blog_profile || blog_post_open_done_) {
            return;
        }
        if(active_post_id_ <= 0) {
            return;
        }

        const String path = String("/blog/api/posts/") + String(active_post_id_) + "?session_token=" + session_token_;
        const HttpResult result = request_json("GET", path);
        print_result("blog_get", result);
        if(result.transport_ok && result.status_code == 200) {
            blog_post_open_done_ = true;
        }
    }

    void maybe_create_support_ticket() {
        if(!config_.support_create_enabled || support_create_done_) {
            return;
        }

        const char* title = value_or_default(config_.support_ticket_title, "M5Cardputer client ticket");
        const char* body = value_or_default(config_.support_ticket_body, "Created from native runtime");
        const String payload = String("{\"session_token\":\"") + json_escape(session_token_) +
                               "\",\"title\":\"" + json_escape(String(title)) + "\",\"body_text\":\"" +
                               json_escape(String(body)) + "\"}";
        const HttpResult result = request_json("POST", "/support/api/tickets", payload);
        print_result("support_create", result);
        ui::on_action("support create", result.transport_ok && result.status_code == 200);
        if(result.transport_ok && result.status_code == 200) {
            support_create_done_ = true;
            const int created_ticket_id = json_find_int(result.body, "ticket_id", 0);
            if(created_ticket_id > 0) {
                active_ticket_id_ = created_ticket_id;
                ui::set_active_ticket(active_ticket_id_);
            }
        }
    }

    void maybe_probe_support_messages() {
        if(!config_.support_profile || support_messages_done_) {
            return;
        }

        const int ticket_id = resolve_ticket_id();
        if(ticket_id <= 0) {
            return;
        }

        const String path = String("/support/api/tickets/") + String(ticket_id) +
                           "/messages?session_token=" + session_token_ + "&limit=20&offset=0";
        const HttpResult result = request_json("GET", path);
        print_result("support_messages", result);
        if(result.transport_ok && result.status_code == 200) {
            support_messages_done_ = true;
        }
    }
};

RuntimeConfig make_m5cardputer_client_standalone_config() {
    RuntimeConfig config = {
        LC_DEVICE_ID,
        LC_DEVICE_TYPE,
        LC_WIFI_SSID,
        LC_WIFI_PASSWORD,
        LC_SERVER_BASE_URL,
        LC_LOGIN,
        LC_PASSWORD,
        LC_CLIENT_KIND,
        LC_LOOP_INTERVAL_MS,
        LC_ACTION_INTERVAL_MS,
        LC_HTTP_TIMEOUT_MS,
        true,
        true,
        true,
        LC_CHAT_SEND_ENABLED,
        LC_SUPPORT_CREATE_ENABLED,
        LC_PREFERRED_CHAT_ID,
        LC_CHAT_MESSAGE_TEXT,
        LC_SUPPORT_TITLE,
        LC_SUPPORT_BODY,
    };
    return config;
}

}  // namespace lc

using namespace lc;

RuntimeConfig kConfig = make_m5cardputer_client_standalone_config();
DeviceRuntime kRuntime(kConfig);

bool is_empty_value(const char* value) {
    return value == nullptr || value[0] == '\0';
}

bool is_default_wifi_ssid(const char* value) {
    return value != nullptr && strcmp(value, "YOUR_WIFI_SSID") == 0;
}

bool is_default_wifi_password(const char* value) {
    return value != nullptr && strcmp(value, "YOUR_WIFI_PASSWORD") == 0;
}

bool validate_runtime_config() {
    bool ok = true;

    if(is_empty_value(kConfig.wifi_ssid) || is_default_wifi_ssid(kConfig.wifi_ssid)) {
        Serial.println("CONFIG ERROR: set LC_WIFI_SSID");
        ui::set_config_error("set LC_WIFI_SSID");
        ok = false;
    }
    if(is_empty_value(kConfig.wifi_password) || is_default_wifi_password(kConfig.wifi_password)) {
        Serial.println("CONFIG ERROR: set LC_WIFI_PASSWORD");
        ui::set_config_error("set LC_WIFI_PASSWORD");
        ok = false;
    }
    if(is_empty_value(kConfig.server_base_url)) {
        Serial.println("CONFIG ERROR: set LC_SERVER_BASE_URL");
        ui::set_config_error("set LC_SERVER_BASE_URL");
        ok = false;
    }
    if(is_empty_value(kConfig.login) || is_empty_value(kConfig.password)) {
        Serial.println("CONFIG ERROR: set LC_LOGIN and LC_PASSWORD");
        ui::set_config_error("set LC_LOGIN and LC_PASSWORD");
        ok = false;
    }
    if(ok) {
        ui::clear_config_error();
    }
    return ok;
}

void halt_for_manual_config() {
    while(true) {
        ui::tick();
        delay(1000);
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    ui::begin(kConfig.device_id);
    ui::set_phase("config check");
    if(!validate_runtime_config()) {
        Serial.println("runtime config invalid; update sketch macros and reflash");
        halt_for_manual_config();
    }
    ui::set_phase("runtime start");
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    ui::tick();
    delay(LC_LOOP_DELAY_MS);
}
