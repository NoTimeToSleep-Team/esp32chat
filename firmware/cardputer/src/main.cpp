// LC Cardputer — этап net.
// Задача: подключиться к Wi-Fi local-chat, проверить сервер (/health) и показать статус.

#include <M5Cardputer.h>
#include <WiFi.h>
#include <HTTPClient.h>

static const char *WIFI_SSID = "local-chat";
static const char *WIFI_PASS = "";
static const char *SERVER_BASE = "http://192.168.4.1:18080";

static bool wifi_ok = false;
static bool wifi_was_attempted = false;
static int last_http_code = 0;
static String last_http_body;
static String last_error;

static void drawScreen() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(TFT_BLACK);
    d.setTextColor(TFT_GREEN, TFT_BLACK);
    d.setTextSize(2);
    d.setCursor(4, 4);
    d.print("LC NET");
    d.setTextSize(1);

    d.setTextColor(TFT_WHITE, TFT_BLACK);
    d.setCursor(4, 30);
    d.printf("WiFi: %s", wifi_ok ? "OK" : (wifi_was_attempted ? "not connected" : "idle"));
    if (wifi_ok) {
        d.setCursor(4, 42);
        d.printf("IP %s  RSSI %d dBm", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
    }

    d.setTextColor(TFT_DARKGREY, TFT_BLACK);
    d.setCursor(4, 58);
    d.printf("srv %s", SERVER_BASE);

    if (last_http_code > 0) {
        d.setTextColor(TFT_CYAN, TFT_BLACK);
        d.setCursor(4, 74);
        d.printf("Health: HTTP %d", last_http_code);
        d.setTextColor(TFT_WHITE, TFT_BLACK);
        d.setCursor(4, 86);
        d.printf("%s", last_http_body.substring(0, 36).c_str());
    } else if (last_error.length() > 0) {
        d.setTextColor(TFT_RED, TFT_BLACK);
        d.setCursor(4, 74);
        d.printf("Health: %s", last_error.c_str());
    } else {
        d.setTextColor(TFT_YELLOW, TFT_BLACK);
        d.setCursor(4, 74);
        d.print("Health: --");
    }

    d.setTextColor(TFT_DARKGREY, TFT_BLACK);
    d.setCursor(4, 122);
    d.print("Enter = retry");
}

static void connectWifi() {
    wifi_was_attempted = true;
    wifi_ok = false;
    drawScreen();

    Serial.printf("wifi: connecting to %s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
        delay(250);
        M5Cardputer.update();
    }

    wifi_ok = (WiFi.status() == WL_CONNECTED);
    if (wifi_ok) {
        Serial.printf("wifi: connected ip=%s rssi=%d channel=%d\n",
                      WiFi.localIP().toString().c_str(), (int)WiFi.RSSI(), (int)WiFi.channel());
    } else {
        last_error = "no wifi";
        Serial.printf("wifi: failed status=%d\n", (int)WiFi.status());
    }
    drawScreen();
}

static void checkHealth() {
    if (WiFi.status() != WL_CONNECTED) {
        wifi_ok = false;
        last_error = "no wifi";
        drawScreen();
        return;
    }
    wifi_ok = true;

    HTTPClient http;
    http.setTimeout(5000);
    String url = String(SERVER_BASE) + "/health";
    http.begin(url);
    int code = http.GET();
    if (code > 0) {
        last_http_code = code;
        last_http_body = http.getString();
        last_error = "";
        Serial.printf("health: HTTP %d body=%s\n", code, last_http_body.substring(0, 200).c_str());
    } else {
        last_http_code = 0;
        last_error = "HTTP " + String(code);
        Serial.printf("health: error %d\n", code);
    }
    http.end();
    drawScreen();
}

void setup() {
    auto cfg = M5.config();
    M5Cardputer.begin(cfg, true);

    Serial.begin(115200);
    delay(300);

    M5Cardputer.Display.setRotation(1);
    drawScreen();

    Serial.println();
    Serial.println("=== LC NET ===");
    Serial.printf("free heap: %lu\n", (unsigned long)ESP.getFreeHeap());

    connectWifi();
    checkHealth();
}

void loop() {
    M5Cardputer.update();

    if (M5Cardputer.Keyboard.isChange() && M5Cardputer.Keyboard.isPressed()) {
        Keyboard_Class::KeysState status = M5Cardputer.Keyboard.keysState();
        if (status.enter) {
            if (WiFi.status() != WL_CONNECTED) {
                connectWifi();
            }
            checkHealth();
        }
    }

    static uint32_t last_health = 0;
    if (millis() - last_health > 15000) {
        last_health = millis();
        checkHealth();
    }

    static uint32_t last_reconnect = 0;
    if (WiFi.status() != WL_CONNECTED && millis() - last_reconnect > 20000) {
        last_reconnect = millis();
        connectWifi();
    }

    static uint32_t last_alive = 0;
    if (millis() - last_alive > 5000) {
        last_alive = millis();
        Serial.printf("alive wifi=%d ip=%s rssi=%d http=%d heap=%lu\n",
                      wifi_ok ? 1 : 0,
                      wifi_ok ? WiFi.localIP().toString().c_str() : "-",
                      wifi_ok ? (int)WiFi.RSSI() : 0,
                      last_http_code,
                      (unsigned long)ESP.getFreeHeap());
    }

    delay(10);
}
