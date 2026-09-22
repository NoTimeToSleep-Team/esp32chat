// LC Cardputer — этап pair.
// Сопряжение по 6-значному коду + вход с proof (HMAC-SHA256), без отправки секрета.

#include <M5Cardputer.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <mbedtls/md.h>
#include <esp_random.h>

static const char *WIFI_SSID = "local-chat";
static const char *WIFI_PASS = "";
static const char *SERVER_BASE = "http://192.168.4.1:18080";
static const char *DEVICE_TYPE = "cardputer";

static Preferences prefs;
static String device_id;
static String device_name;
static uint8_t device_secret[32];
static uint8_t device_secret_hash[32];

static String pairing_id;
static String pairing_code;
static String session_token;
static String session_login;
static bool paired = false;
static String status_line = "boot";
static String last_error;

static void drawScreen();
static void requestPairingCode();
static void pollPairingStatus();
static void runDeviceSession();

// --- helpers ---

static String toHex(const uint8_t *data, size_t len) {
    static const char *digits = "0123456789abcdef";
    String out;
    out.reserve(len * 2);
    for (size_t i = 0; i < len; i++) {
        out += digits[data[i] >> 4];
        out += digits[data[i] & 0x0F];
    }
    return out;
}

static void sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
    const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    mbedtls_md(info, data, len, out);
}

static String hmacSha256Hex(const uint8_t *key, size_t key_len, const String &message) {
    uint8_t out[32];
    const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    mbedtls_md_hmac(info, key, key_len, (const unsigned char *)message.c_str(), message.length(), out);
    return toHex(out, sizeof(out));
}

static String jsonString(const String &body, const char *key) {
    int idx = body.indexOf(key);
    if (idx < 0) {
        return "";
    }
    idx += strlen(key);
    int end = body.indexOf('"', idx);
    if (end < 0) {
        return "";
    }
    return body.substring(idx, end);
}

static int httpGet(const String &path, String &response) {
    HTTPClient http;
    http.setTimeout(6000);
    if (!http.begin(String(SERVER_BASE) + path)) {
        response = "";
        return -1000;
    }
    int code = http.GET();
    response = (code > 0) ? http.getString() : "";
    http.end();
    return code;
}

static int httpPostJson(const String &path, const String &body, String &response) {
    HTTPClient http;
    http.setTimeout(6000);
    if (!http.begin(String(SERVER_BASE) + path)) {
        response = "";
        return -1000;
    }
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    response = (code > 0) ? http.getString() : "";
    http.end();
    return code;
}

// --- screen ---

static void drawScreen() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(TFT_BLACK);
    d.setTextColor(TFT_GREEN, TFT_BLACK);
    d.setTextSize(2);
    d.setCursor(4, 4);
    d.print("LC PAIR");

    d.setTextSize(1);
    d.setTextColor(TFT_DARKGREY, TFT_BLACK);
    d.setCursor(4, 26);
    d.printf("%s", device_id.c_str());

    if (pairing_code.length() == 6 && !paired) {
        d.setTextColor(TFT_WHITE, TFT_BLACK);
        d.setCursor(4, 42);
        d.print("Pairing code:");
        d.setTextSize(3);
        d.setTextColor(TFT_CYAN, TFT_BLACK);
        d.setCursor(4, 56);
        d.print(pairing_code);
        d.setTextSize(1);
        d.setTextColor(TFT_YELLOW, TFT_BLACK);
        d.setCursor(4, 92);
        d.print("Enter it in web UI:");
        d.setCursor(4, 104);
        d.print("Devices -> Pair by code");
    } else if (paired && session_token.length() > 0) {
        d.setTextColor(TFT_GREEN, TFT_BLACK);
        d.setCursor(4, 46);
        d.print("Session OK");
        d.setTextColor(TFT_WHITE, TFT_BLACK);
        d.setCursor(4, 60);
        d.printf("user: %s", session_login.c_str());
    } else if (paired) {
        d.setTextColor(TFT_GREEN, TFT_BLACK);
        d.setCursor(4, 46);
        d.print("Paired");
    } else {
        d.setTextColor(TFT_YELLOW, TFT_BLACK);
        d.setCursor(4, 46);
        d.print("No code yet");
    }

    d.setTextColor(TFT_DARKGREY, TFT_BLACK);
    d.setCursor(4, 120);
    d.printf("Enter = retry");
    d.setCursor(120, 120);
    d.printf("%s", status_line.c_str());
}

// --- network flow ---

static void connectWifi() {
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    status_line = "wifi...";
    drawScreen();
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
        delay(250);
        M5Cardputer.update();
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("wifi: ip=%s rssi=%d\n", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
        status_line = "wifi ok";
    } else {
        status_line = "wifi failed";
        last_error = "wifi";
    }
    drawScreen();
}

static void requestPairingCode() {
    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
        if (WiFi.status() != WL_CONNECTED) {
            return;
        }
    }
    status_line = "requesting...";
    drawScreen();

    String secret_hash_hex = toHex(device_secret_hash, sizeof(device_secret_hash));
    String body = String("{\"device_id\":\"") + device_id +
                  "\",\"device_type\":\"" + DEVICE_TYPE +
                  "\",\"name\":\"" + device_name +
                  "\",\"device_secret_hash\":\"" + secret_hash_hex + "\"}";

    String response;
    int code = httpPostJson("/devices/api/pair/request", body, response);
    Serial.printf("pair/request: HTTP %d %s\n", code, response.c_str());

    if (code != 200) {
        status_line = "request failed";
        last_error = String("http ") + code;
        drawScreen();
        return;
    }

    pairing_id = jsonString(response, "\"pairing_id\":\"");
    pairing_code = jsonString(response, "\"code\":\"");
    if (pairing_id.length() != 32 || pairing_code.length() != 6) {
        status_line = "bad response";
        last_error = "parse";
        drawScreen();
        return;
    }
    status_line = "waiting";
    drawScreen();
}

static void pollPairingStatus() {
    if (pairing_id.length() != 32) {
        return;
    }
    String response;
    int code = httpGet(String("/devices/api/pair/status?pairing_id=") + pairing_id, response);
    if (code != 200) {
        Serial.printf("pair/status: HTTP %d\n", code);
        return;
    }
    String state = jsonString(response, "\"pairing_status\":\"");
    Serial.printf("pair/status: %s\n", state.c_str());
    if (state == "claimed") {
        paired = true;
        prefs.putBool("paired", true);
        pairing_code = "";
        status_line = "paired!";
        drawScreen();
        runDeviceSession();
    } else if (state == "expired") {
        status_line = "code expired";
        pairing_code = "";
        pairing_id = "";
        drawScreen();
    }
}

static void runDeviceSession() {
    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
        if (WiFi.status() != WL_CONNECTED) {
            return;
        }
    }
    status_line = "signing in...";
    drawScreen();

    String response;
    String challenge_body = String("{\"device_id\":\"") + device_id + "\"}";
    int code = httpPostJson("/auth/device-challenge", challenge_body, response);
    Serial.printf("device-challenge: HTTP %d %s\n", code, response.c_str());
    if (code != 200) {
        status_line = "challenge failed";
        if (code == 404) {
            paired = false;
            prefs.putBool("paired", false);
            pairing_id = "";
            pairing_code = "";
        }
        drawScreen();
        return;
    }

    String challenge = jsonString(response, "\"challenge\":\"");
    if (challenge.length() != 32) {
        status_line = "bad challenge";
        drawScreen();
        return;
    }

    String proof = hmacSha256Hex(device_secret_hash, sizeof(device_secret_hash), challenge);
    String session_body = String("{\"device_id\":\"") + device_id +
                          "\",\"challenge\":\"" + challenge +
                          "\",\"proof\":\"" + proof + "\"}";
    code = httpPostJson("/auth/device-session", session_body, response);
    Serial.printf("device-session: HTTP %d %s\n", code, response.c_str());
    if (code != 200) {
        status_line = "session failed";
        if (code == 404 || code == 401) {
            paired = false;
            prefs.putBool("paired", false);
            pairing_id = "";
        }
        drawScreen();
        return;
    }

    session_token = jsonString(response, "\"token\":\"");
    session_login = jsonString(response, "\"login\":\"");
    status_line = "session ok";
    Serial.printf("session: user=%s token_len=%u heap=%lu\n",
                  session_login.c_str(), (unsigned)session_token.length(),
                  (unsigned long)ESP.getFreeHeap());
    drawScreen();
}

// --- arduino ---

void setup() {
    auto cfg = M5.config();
    M5Cardputer.begin(cfg, true);

    Serial.begin(115200);
    delay(300);

    M5Cardputer.Display.setRotation(1);
    drawScreen();

    Serial.println();
    Serial.println("=== LC PAIR ===");

    prefs.begin("lc", false);
    size_t stored = prefs.getBytesLength("secret");
    if (stored != sizeof(device_secret)) {
        esp_fill_random(device_secret, sizeof(device_secret));
        prefs.putBytes("secret", device_secret, sizeof(device_secret));
        Serial.println("secret: generated");
    } else {
        prefs.getBytes("secret", device_secret, sizeof(device_secret));
        Serial.println("secret: loaded");
    }
    paired = prefs.getBool("paired", false);
    sha256(device_secret, sizeof(device_secret), device_secret_hash);

    WiFi.mode(WIFI_STA);
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char idbuf[24];
    snprintf(idbuf, sizeof(idbuf), "cp-%02x%02x%02x%02x%02x%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    device_id = String(idbuf);
    char namebuf[24];
    snprintf(namebuf, sizeof(namebuf), "Cardputer %02X%02X", mac[4], mac[5]);
    device_name = String(namebuf);

    Serial.printf("device_id: %s\n", device_id.c_str());
    Serial.printf("paired flag: %d\n", paired ? 1 : 0);
    Serial.printf("free heap: %lu\n", (unsigned long)ESP.getFreeHeap());

    connectWifi();
    if (paired) {
        runDeviceSession();
    } else {
        requestPairingCode();
    }
}

void loop() {
    M5Cardputer.update();

    if (M5Cardputer.Keyboard.isChange() && M5Cardputer.Keyboard.isPressed()) {
        Keyboard_Class::KeysState status = M5Cardputer.Keyboard.keysState();
        if (status.enter) {
            if (paired) {
                runDeviceSession();
            } else {
                requestPairingCode();
            }
        }
    }

    static uint32_t last_poll = 0;
    if (!paired && pairing_id.length() == 32 && millis() - last_poll > 2000) {
        last_poll = millis();
        pollPairingStatus();
    }

    static uint32_t last_retry = 0;
    if (paired && session_token.length() == 0 && millis() - last_retry > 15000) {
        last_retry = millis();
        runDeviceSession();
    }

    static uint32_t last_alive = 0;
    if (millis() - last_alive > 5000) {
        last_alive = millis();
        Serial.printf("alive wifi=%d paired=%d session=%d status=%s heap=%lu\n",
                      WiFi.status() == WL_CONNECTED ? 1 : 0,
                      paired ? 1 : 0,
                      session_token.length() > 0 ? 1 : 0,
                      status_line.c_str(),
                      (unsigned long)ESP.getFreeHeap());
    }

    delay(10);
}
