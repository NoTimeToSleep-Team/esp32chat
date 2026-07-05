/*
 * M5Stamp S3 service firmware (standalone single-file sketch).
 *
 * Fill required macros below, compile in Arduino IDE for ESP32, then flash.
 *
 * NOTE:
 * - Standalone runtime based on firmware/arduino/common/local_chat_runtime.h
 * - Standalone preset equivalent of firmware/arduino/presets/m5stamp_s3_preset.h
 */

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>

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

#ifndef LC_OPS_SESSION_TOKEN
#define LC_OPS_SESSION_TOKEN ""
#endif

#ifndef LC_DEVICE_ID
#define LC_DEVICE_ID "m5stamp-s3-01"
#endif

#ifndef LC_DEVICE_TYPE
#define LC_DEVICE_TYPE "m5stamp_s3"
#endif

#ifndef LC_LOOP_DELAY_MS
#define LC_LOOP_DELAY_MS 25
#endif

#ifndef LC_LOOP_INTERVAL_MS
#define LC_LOOP_INTERVAL_MS 1500
#endif

#ifndef LC_HEARTBEAT_INTERVAL_MS
#define LC_HEARTBEAT_INTERVAL_MS 15000
#endif

#ifndef LC_TELEMETRY_INTERVAL_MS
#define LC_TELEMETRY_INTERVAL_MS 45000
#endif

#ifndef LC_HTTP_TIMEOUT_MS
#define LC_HTTP_TIMEOUT_MS 5000
#endif

namespace lc {

struct RuntimeConfig {
    const char* device_id;
    const char* device_type;
    const char* wifi_ssid;
    const char* wifi_password;
    const char* server_base_url;
    const char* ops_session_token;
    unsigned long loop_interval_ms;
    unsigned long heartbeat_interval_ms;
    unsigned long telemetry_interval_ms;
    int http_timeout_ms;
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

class DeviceRuntime {
public:
    explicit DeviceRuntime(const RuntimeConfig& config)
        : config_(config),
          last_loop_ms_(0),
          last_heartbeat_ms_(0),
          last_telemetry_ms_(0),
          registered_(false) {
    }

    void begin() {
        Serial.println("m5stamp s3 service runtime: boot");
        Serial.print("device_id=");
        Serial.println(config_.device_id);
        Serial.print("device_type=");
        Serial.println(config_.device_type);

        connect_wifi_blocking(15000);
        probe_health();
        register_device();
        send_heartbeat();
        send_telemetry();
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

        register_device();

        if(now_ms - last_heartbeat_ms_ >= config_.heartbeat_interval_ms) {
            send_heartbeat();
        }
        if(now_ms - last_telemetry_ms_ >= config_.telemetry_interval_ms) {
            send_telemetry();
        }
    }

private:
    RuntimeConfig config_;
    unsigned long last_loop_ms_;
    unsigned long last_heartbeat_ms_;
    unsigned long last_telemetry_ms_;
    bool registered_;

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
                               "\",\"status\":\"active\",\"metadata_json\":{\"firmware\":\"arduino-single\"}}";
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
};

RuntimeConfig make_m5stamp_s3_standalone_config() {
    RuntimeConfig config = {
        LC_DEVICE_ID,
        LC_DEVICE_TYPE,
        LC_WIFI_SSID,
        LC_WIFI_PASSWORD,
        LC_SERVER_BASE_URL,
        LC_OPS_SESSION_TOKEN,
        LC_LOOP_INTERVAL_MS,
        LC_HEARTBEAT_INTERVAL_MS,
        LC_TELEMETRY_INTERVAL_MS,
        LC_HTTP_TIMEOUT_MS,
    };
    return config;
}

}  // namespace lc

using namespace lc;

RuntimeConfig kConfig = make_m5stamp_s3_standalone_config();
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
        ok = false;
    }
    if(is_empty_value(kConfig.wifi_password) || is_default_wifi_password(kConfig.wifi_password)) {
        Serial.println("CONFIG ERROR: set LC_WIFI_PASSWORD");
        ok = false;
    }
    if(is_empty_value(kConfig.server_base_url)) {
        Serial.println("CONFIG ERROR: set LC_SERVER_BASE_URL");
        ok = false;
    }
    if(is_empty_value(kConfig.ops_session_token)) {
        Serial.println("CONFIG ERROR: set LC_OPS_SESSION_TOKEN");
        ok = false;
    }
    return ok;
}

void halt_for_manual_config() {
    while(true) {
        delay(1000);
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    if(!validate_runtime_config()) {
        Serial.println("runtime config invalid; update sketch macros and reflash");
        halt_for_manual_config();
    }
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(LC_LOOP_DELAY_MS);
}
