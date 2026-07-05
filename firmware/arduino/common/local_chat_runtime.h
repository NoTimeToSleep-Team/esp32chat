#pragma once

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>

#include <string.h>

namespace lc {

struct RuntimeConfig {
    const char* device_id;
    const char* device_type;
    const char* wifi_ssid;
    const char* wifi_password;
    const char* server_base_url;
    const char* ops_session_token;
    const char* login;
    const char* password;
    const char* client_kind;
    bool service_profile;
    bool auth_profile;
    bool chat_profile;
    bool blog_profile;
    bool support_profile;
    bool admin_profile;
    unsigned long loop_interval_ms;
    unsigned long heartbeat_interval_ms;
    unsigned long telemetry_interval_ms;
    int http_timeout_ms;

    unsigned long action_interval_ms;
    bool chat_send_enabled;
    bool support_create_enabled;
    bool admin_reply_enabled;
    bool admin_resolve_enabled;
    bool admin_blog_publish_enabled;

    int preferred_chat_id;
    int preferred_ticket_id;

    const char* chat_message_text;
    const char* support_ticket_title;
    const char* support_ticket_body;
    const char* admin_reply_text;
    const char* admin_blog_title;
    const char* admin_blog_body;
};

struct HttpResult {
    int status_code;
    bool transport_ok;
    String body;
};

inline String json_escape(const String& value) {
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

inline String trim_base_url(const char* input) {
    String out = String(input == nullptr ? "" : input);
    while(out.length() > 0 && out.endsWith("/")) {
        out.remove(out.length() - 1);
    }
    return out;
}

inline String build_url(const char* base_url, const String& path) {
    const String base = trim_base_url(base_url);
    if(path.startsWith("/")) {
        return base + path;
    }
    return base + "/" + path;
}

inline String json_find_string(const String& body, const char* key) {
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

inline int json_find_int(const String& body, const char* key, int fallback = 0) {
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
          last_heartbeat_ms_(0),
          last_telemetry_ms_(0),
          registered_(false),
          active_chat_id_(0),
          active_post_id_(0),
          active_ticket_id_(0),
          chat_send_done_(false),
          chat_history_done_(false),
          blog_post_open_done_(false),
          support_create_done_(false),
          support_messages_done_(false),
          admin_reply_done_(false),
          admin_messages_done_(false),
          admin_resolve_done_(false),
          admin_blog_done_(false) {
    }

    void begin() {
        Serial.begin(115200);
        delay(200);
        Serial.println("local-chat runtime: boot");
        Serial.print("device_id=");
        Serial.println(config_.device_id);
        Serial.print("device_type=");
        Serial.println(config_.device_type);

        connect_wifi_blocking(15000);
        probe_health();

        if(config_.service_profile) {
            register_device();
            send_heartbeat();
            send_telemetry();
        }

        if(config_.auth_profile || config_.chat_profile || config_.blog_profile || config_.support_profile ||
           config_.admin_profile) {
            ensure_session();
        }
    }

    void loop() {
        const unsigned long now_ms = millis();
        if(now_ms - last_loop_ms_ < config_.loop_interval_ms) {
            return;
        }
        last_loop_ms_ = now_ms;

        if(WiFi.status() != WL_CONNECTED) {
            connect_wifi_blocking(8000);
            return;
        }

        if(config_.service_profile) {
            register_device();
            if(now_ms - last_heartbeat_ms_ >= config_.heartbeat_interval_ms) {
                send_heartbeat();
            }
            if(now_ms - last_telemetry_ms_ >= config_.telemetry_interval_ms) {
                send_telemetry();
            }
        }

        if(config_.auth_profile || config_.chat_profile || config_.blog_profile || config_.support_profile ||
           config_.admin_profile) {
            ensure_session();
            run_client_probes();

            const unsigned long action_interval =
                (config_.action_interval_ms > 0) ? config_.action_interval_ms : 15000;
            if(now_ms - last_action_ms_ >= action_interval) {
                run_client_actions();
                last_action_ms_ = now_ms;
            }
        }
    }

private:
    RuntimeConfig config_;
    unsigned long last_loop_ms_;
    unsigned long last_action_ms_;
    unsigned long last_heartbeat_ms_;
    unsigned long last_telemetry_ms_;
    bool registered_;
    int active_chat_id_;
    int active_post_id_;
    int active_ticket_id_;
    bool chat_send_done_;
    bool chat_history_done_;
    bool blog_post_open_done_;
    bool support_create_done_;
    bool support_messages_done_;
    bool admin_reply_done_;
    bool admin_messages_done_;
    bool admin_resolve_done_;
    bool admin_blog_done_;
    String session_token_;

    bool connect_wifi_blocking(unsigned long timeout_ms) {
        if(config_.wifi_ssid == nullptr || strlen(config_.wifi_ssid) == 0) {
            Serial.println("wifi ssid not configured");
            return false;
        }
        if(WiFi.status() == WL_CONNECTED) {
            return true;
        }

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
        } else {
            Serial.println("wifi connect timeout");
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
                return true;
            }
        }
        return false;
    }

    void register_device() {
        if(registered_) {
            return;
        }
        if(config_.ops_session_token == nullptr || strlen(config_.ops_session_token) == 0) {
            return;
        }

        const String payload = String("{\"session_token\":\"") +
                               json_escape(String(config_.ops_session_token)) + "\",\"device_id\":\"" +
                               json_escape(String(config_.device_id)) + "\",\"device_type\":\"" +
                               json_escape(String(config_.device_type)) +
                               "\",\"status\":\"active\",\"metadata_json\":{\"firmware\":\"arduino\"}}";
        const HttpResult result = request_json("POST", "/ops/api/devices/register", payload);
        print_result("ops_register", result);
        if(result.transport_ok && result.status_code == 200) {
            registered_ = true;
        }
    }

    void send_heartbeat() {
        if(config_.ops_session_token == nullptr || strlen(config_.ops_session_token) == 0) {
            return;
        }
        const String payload = String("{\"session_token\":\"") +
                               json_escape(String(config_.ops_session_token)) + "\",\"device_id\":\"" +
                               json_escape(String(config_.device_id)) +
                               "\",\"status\":\"active\",\"uptime_ms\":" + String(millis()) + "}";
        const HttpResult result = request_json("POST", "/ops/api/devices/heartbeat", payload);
        print_result("ops_heartbeat", result);
        if(result.transport_ok && result.status_code == 200) {
            last_heartbeat_ms_ = millis();
        }
    }

    void send_telemetry() {
        if(config_.ops_session_token == nullptr || strlen(config_.ops_session_token) == 0) {
            return;
        }
        const int32_t rssi = WiFi.RSSI();
        const String payload = String("{\"session_token\":\"") +
                               json_escape(String(config_.ops_session_token)) + "\",\"device_id\":\"" +
                               json_escape(String(config_.device_id)) +
                               "\",\"telemetry_json\":{\"wifi_rssi\":" + String(rssi) +
                               ",\"uptime_ms\":" + String(millis()) + "}}";
        const HttpResult result = request_json("POST", "/ops/api/devices/telemetry", payload);
        print_result("ops_telemetry", result);
        if(result.transport_ok && result.status_code == 200) {
            last_telemetry_ms_ = millis();
        }
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
        }

        if(config_.admin_profile) {
            const String path = String("/admin/content/support/tickets?session_token=") + session_token_ +
                               "&limit=5&offset=0";
            const HttpResult result = request_json("GET", path);
            print_result("admin_support_queue", result);
            const int parsed_ticket_id = json_find_int(result.body, "ticket_id", 0);
            if(active_ticket_id_ <= 0 && parsed_ticket_id > 0) {
                active_ticket_id_ = parsed_ticket_id;
            }
        }
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

        maybe_publish_admin_blog();

        maybe_send_admin_reply();
        maybe_probe_admin_messages();

        maybe_resolve_admin_ticket();
    }

    const char* value_or_default(const char* input, const char* fallback) {
        if(input == nullptr || strlen(input) == 0) {
            return fallback;
        }
        return input;
    }

    int resolve_chat_id() const {
        if(config_.preferred_chat_id > 0) {
            return config_.preferred_chat_id;
        }
        return active_chat_id_;
    }

    int resolve_ticket_id() const {
        if(config_.preferred_ticket_id > 0) {
            return config_.preferred_ticket_id;
        }
        return active_ticket_id_;
    }

    void maybe_send_chat_message() {
        if(!config_.chat_send_enabled || chat_send_done_) {
            return;
        }
        const int chat_id = resolve_chat_id();
        if(chat_id <= 0) {
            return;
        }

        const char* message_text = value_or_default(config_.chat_message_text, "hello from arduino runtime");
        const String payload = String("{\"session_token\":\"") + json_escape(session_token_) +
                               "\",\"body_text\":\"" + json_escape(String(message_text)) +
                               "\",\"client_message_id\":\"arduino-" + String(millis()) + "\"}";
        const String path = String("/chat/api/chats/") + String(chat_id) + "/messages";
        const HttpResult result = request_json("POST", path, payload);
        print_result("chat_send", result);
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

        const char* title = value_or_default(config_.support_ticket_title, "Device Support Ticket");
        const char* body = value_or_default(config_.support_ticket_body, "Created by native Arduino runtime");
        const String payload = String("{\"session_token\":\"") + json_escape(session_token_) +
                               "\",\"title\":\"" + json_escape(String(title)) + "\",\"body_text\":\"" +
                               json_escape(String(body)) + "\"}";
        const HttpResult result = request_json("POST", "/support/api/tickets", payload);
        print_result("support_create", result);
        if(result.transport_ok && result.status_code == 200) {
            support_create_done_ = true;
            const int created_ticket_id = json_find_int(result.body, "ticket_id", 0);
            if(created_ticket_id > 0) {
                active_ticket_id_ = created_ticket_id;
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

    void maybe_publish_admin_blog() {
        if(!config_.admin_blog_publish_enabled || admin_blog_done_) {
            return;
        }

        const char* title = value_or_default(config_.admin_blog_title, "Admin blog from native runtime");
        const char* body = value_or_default(config_.admin_blog_body, "Published by Arduino admin flow");
        const String payload = String("{\"session_token\":\"") + json_escape(session_token_) +
                               "\",\"title\":\"" + json_escape(String(title)) + "\",\"body_text\":\"" +
                               json_escape(String(body)) + "\"}";
        const HttpResult result = request_json("POST", "/admin/content/blog/posts", payload);
        print_result("admin_blog_publish", result);
        if(result.transport_ok && result.status_code == 200) {
            admin_blog_done_ = true;
        }
    }

    void maybe_send_admin_reply() {
        if(!config_.admin_reply_enabled || admin_reply_done_) {
            return;
        }

        const int ticket_id = resolve_ticket_id();
        if(ticket_id <= 0) {
            return;
        }

        const char* body = value_or_default(config_.admin_reply_text, "Admin reply from native runtime");
        const String payload = String("{\"session_token\":\"") + json_escape(session_token_) +
                               "\",\"body_text\":\"" + json_escape(String(body)) + "\"}";
        const String path = String("/admin/content/support/tickets/") + String(ticket_id) + "/reply";
        const HttpResult result = request_json("POST", path, payload);
        print_result("admin_support_reply", result);
        if(result.transport_ok && result.status_code == 200) {
            admin_reply_done_ = true;
        }
    }

    void maybe_probe_admin_messages() {
        if(!config_.admin_profile || admin_messages_done_) {
            return;
        }

        const int ticket_id = resolve_ticket_id();
        if(ticket_id <= 0) {
            return;
        }

        const String path = String("/admin/content/support/tickets/") + String(ticket_id) +
                           "/messages?session_token=" + session_token_ + "&limit=20&offset=0";
        const HttpResult result = request_json("GET", path);
        print_result("admin_support_messages", result);
        if(result.transport_ok && result.status_code == 200) {
            admin_messages_done_ = true;
        }
    }

    void maybe_resolve_admin_ticket() {
        if(!config_.admin_resolve_enabled || admin_resolve_done_) {
            return;
        }

        const int ticket_id = resolve_ticket_id();
        if(ticket_id <= 0) {
            return;
        }

        const String payload = String("{\"session_token\":\"") + json_escape(session_token_) +
                               "\",\"status\":\"resolved\"}";
        const String path = String("/admin/content/support/tickets/") + String(ticket_id) + "/status";
        const HttpResult result = request_json("POST", path, payload);
        print_result("admin_support_resolve", result);
        if(result.transport_ok && result.status_code == 200) {
            admin_resolve_done_ = true;
        }
    }
};

}  // namespace lc
