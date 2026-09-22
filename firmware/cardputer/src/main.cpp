// LC Cardputer — этапы pair + chat.
// Сопряжение по 6-значному коду, вход с HMAC-proof, список чатов, лента, отправка.

#include <M5Cardputer.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <mbedtls/md.h>
#include <esp_random.h>
#include <ArduinoJson.h>

#include "lc_font_10.h"

static const char *WIFI_SSID = "local-chat";
static const char *WIFI_PASS = "";
static const char *SERVER_BASE = "http://192.168.4.1:18080";
static const char *DEVICE_TYPE = "cardputer";

static const int MAX_CHATS = 16;
static const int MAX_MSGS = 60;
static const int MSG_POLL_MS = 3000;

// --- pair state ---
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
static String pair_status = "boot";
static uint64_t last_seen_ms = 0;

// --- chat state ---
enum class Screen { PAIR, MENU, CHAT_LIST, CHAT_VIEW, CHAT_INPUT, BLOG_LIST, BLOG_VIEW, SUPPORT_LIST, SUPPORT_VIEW, SUPPORT_INPUT, SUPPORT_NEW, SETTINGS, ABOUT };
static Screen screen = Screen::PAIR;

struct ChatItem {
    long id;
    String title;
};
struct MsgItem {
    long id;
    String author;
    String text;
    String file;
};

static ChatItem chats[MAX_CHATS];
static int chat_count = 0;
static int chat_sel = 0;

static MsgItem msgs[MAX_MSGS];
static int msg_count = 0;
static int msg_scroll = 0;
static long last_msg_id = 0;

static long current_chat_id = 0;
static String current_chat_title;
static String input_text;
static String net_status;

static const int MAX_BLOG = 16;
struct BlogItem {
    long id;
    String title;
};
static BlogItem blog[MAX_BLOG];
static int blog_count = 0;
static int blog_sel = 0;
static String post_title;
static std::vector<String> post_lines;
static int post_scroll = 0;

static const int MENU_ITEMS = 5;
static const char *menu_titles[MENU_ITEMS] = {"Чат", "Блог", "Поддержка", "Настройки", "О проекте"};
static int menu_sel = 0;

static const int BRIGHT_LEVELS[4] = {64, 128, 191, 255};
static const char *BRIGHT_LABELS[4] = {"25%", "50%", "75%", "100%"};
static const int VOLUME_LEVELS[5] = {0, 64, 128, 191, 255};
static const char *VOLUME_LABELS[5] = {"Выкл", "25%", "50%", "75%", "100%"};
static const int SLEEP_MS[4] = {0, 30000, 60000, 300000};
static const char *SLEEP_LABELS[4] = {"Выкл", "30 сек", "1 мин", "5 мин"};
static const uint8_t LED_COLORS[6][3] = {
    {255, 255, 255}, {255, 0, 0}, {0, 255, 0}, {0, 0, 255}, {255, 160, 0}, {170, 0, 255}};
static const char *LED_COLOR_LABELS[6] = {"Белый", "Красный", "Зелёный", "Синий", "Жёлтый", "Фиолетовый"};

static int setting_bright = 3;
static bool setting_sound = true;
static int setting_volume = 1;
static int setting_sleep = 0;
static bool setting_notify = true;
static bool setting_led = false;
static int setting_led_color = 0;
static bool setting_clock = true;
static int setting_tz = 3;
static bool setting_wifi_sleep = false;
static bool screen_off = false;
static uint32_t last_activity_ms = 0;
static int64_t clock_offset_ms = 0;
static bool clock_valid = false;

enum SettingId {
    SET_BRIGHT,
    SET_SOUND,
    SET_VOLUME,
    SET_SLEEP,
    SET_NOTIFY,
    SET_LED,
    SET_LED_COLOR,
    SET_CLOCK,
    SET_TZ,
    SET_WIFI_SLEEP,
    SET_RESET,
    SET_REBOOT,
};
static const int SETTINGS_ORDER[] = {
    SET_BRIGHT, SET_SOUND, SET_VOLUME, SET_SLEEP, SET_NOTIFY,
    SET_CLOCK, SET_TZ, SET_WIFI_SLEEP,
    SET_RESET, SET_REBOOT,
};
static const char *SETTINGS_LABELS[] = {
    "Яркость", "Звук", "Громкость", "Гашение экрана", "Уведомления",
    "LED подсветка", "Цвет LED", "Часы", "Часовой пояс", "Wi-Fi сон",
    "Сброс настроек", "Перезагрузка",
};
static const int SETTINGS_COUNT = 10;
static const int SETTINGS_VISIBLE = 5;
static int settings_sel = 0;
static int settings_scroll = 0;

static const int MAX_TICKETS = 12;
struct TicketItem {
    long id;
    String title;
    String status;
};
static TicketItem tickets[MAX_TICKETS];
static int ticket_count = 0;
static int ticket_sel = 0;
static long current_ticket_id = 0;
static String current_ticket_title;

static const char *FW_VERSION = "0.3.0";
static std::vector<String> about_lines;
static int about_scroll = 0;

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

static String escapeJson(const String &in) {
    String out;
    out.reserve(in.length() + 8);
    for (size_t i = 0; i < in.length(); i++) {
        char c = in[i];
        if (c == '"' || c == '\\') {
            out += '\\';
            out += c;
        } else if (c == '\n') {
            out += "\\n";
        } else if ((unsigned char)c >= 0x20) {
            out += c;
        }
    }
    return out;
}

static String clip(const String &s, int max_chars) {
    if ((int)s.length() <= max_chars) {
        return s;
    }
    return s.substring(0, max_chars - 1) + "~";
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

// --- forward declarations ---

static void drawScreen();
static void drawPairScreen();
static void drawMenu();
static String formatClock();
static void runDeviceSession();
static void initUpdatesCursor();
static void pollUpdates();
static bool loadChats();

// --- pair ---

static void drawPairScreen() {
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
        d.setCursor(4, 36);
        d.print("Pairing code:");
        d.setTextSize(3);
        d.setTextColor(TFT_CYAN, TFT_BLACK);
        d.setCursor(4, 48);
        d.print(pairing_code);
        d.setTextSize(1);
        d.setTextColor(TFT_YELLOW, TFT_BLACK);
        d.setCursor(4, 94);
        d.print("Enter it in web UI:");
        d.setCursor(4, 108);
        d.print("Devices -> Pair by code");
    } else if (paired && session_token.length() > 0) {
        d.setTextColor(TFT_GREEN, TFT_BLACK);
        d.setCursor(4, 46);
        d.print("Session OK");
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
    d.printf("%s", pair_status.c_str());
}

static void connectWifi() {
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    pair_status = "wifi...";
    if (screen == Screen::PAIR) {
        drawPairScreen();
    }
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(WIFI_SSID, WIFI_PASS);    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
        delay(250);
        M5Cardputer.update();
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("wifi: ip=%s rssi=%d\n", WiFi.localIP().toString().c_str(), (int)WiFi.RSSI());
        pair_status = "wifi ok";
        WiFi.setSleep(setting_wifi_sleep);
    } else {
        pair_status = "wifi failed";
    }
    if (screen == Screen::PAIR) {
        drawPairScreen();
    }
}

static void requestPairingCode() {
    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
        if (WiFi.status() != WL_CONNECTED) {
            return;
        }
    }
    pair_status = "requesting...";
    drawPairScreen();

    String secret_hash_hex = toHex(device_secret_hash, sizeof(device_secret_hash));
    String body = String("{\"device_id\":\"") + device_id +
                  "\",\"device_type\":\"" + DEVICE_TYPE +
                  "\",\"name\":\"" + device_name +
                  "\",\"device_secret_hash\":\"" + secret_hash_hex + "\"}";

    String response;
    int code = httpPostJson("/devices/api/pair/request", body, response);
    Serial.printf("pair/request: HTTP %d %s\n", code, response.c_str());

    if (code != 200) {
        pair_status = "request failed";
        drawPairScreen();
        return;
    }

    pairing_id = jsonString(response, "\"pairing_id\":\"");
    pairing_code = jsonString(response, "\"code\":\"");
    if (pairing_id.length() != 32 || pairing_code.length() != 6) {
        pair_status = "bad response";
        drawPairScreen();
        return;
    }
    pair_status = "waiting";
    drawPairScreen();
}

static void pollPairingStatus() {
    if (pairing_id.length() != 32) {
        return;
    }
    String response;
    int code = httpGet(String("/devices/api/pair/status?pairing_id=") + pairing_id, response);
    if (code != 200) {
        return;
    }
    String state = jsonString(response, "\"pairing_status\":\"");
    Serial.printf("pair/status: %s\n", state.c_str());
    if (state == "claimed") {
        paired = true;
        prefs.putBool("paired", true);
        pairing_code = "";
        pair_status = "paired!";
        drawPairScreen();
        runDeviceSession();
    } else if (state == "expired") {
        pair_status = "code expired";
        pairing_code = "";
        pairing_id = "";
        drawPairScreen();
    }
}

static void runDeviceSession() {
    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
        if (WiFi.status() != WL_CONNECTED) {
            return;
        }
    }
    pair_status = "signing in...";
    if (screen == Screen::PAIR) {
        drawPairScreen();
    }

    String response;
    String challenge_body = String("{\"device_id\":\"") + device_id + "\"}";
    int code = httpPostJson("/auth/device-challenge", challenge_body, response);
    Serial.printf("device-challenge: HTTP %d\n", code);
    if (code != 200) {
        pair_status = "challenge failed";
        if (code == 404) {
            paired = false;
            prefs.putBool("paired", false);
            pairing_id = "";
            pairing_code = "";
        }
        if (screen == Screen::PAIR) {
            drawPairScreen();
        }
        return;
    }

    String challenge = jsonString(response, "\"challenge\":\"");
    if (challenge.length() != 32) {
        pair_status = "bad challenge";
        drawPairScreen();
        return;
    }

    String proof = hmacSha256Hex(device_secret_hash, sizeof(device_secret_hash), challenge);
    String session_body = String("{\"device_id\":\"") + device_id +
                          "\",\"challenge\":\"" + challenge +
                          "\",\"proof\":\"" + proof + "\"}";
    code = httpPostJson("/auth/device-session", session_body, response);
    Serial.printf("device-session: HTTP %d\n", code);
    if (code != 200) {
        pair_status = "session failed";
        if (code == 404 || code == 401) {
            paired = false;
            prefs.putBool("paired", false);
            pairing_id = "";
        }
        if (screen == Screen::PAIR) {
            drawPairScreen();
        }
        return;
    }

    session_token = jsonString(response, "\"token\":\"");
    session_login = jsonString(response, "\"login\":\"");
    pair_status = "session ok";
    Serial.printf("session: user=%s token_len=%u\n", session_login.c_str(), (unsigned)session_token.length());

    initUpdatesCursor();

    screen = Screen::MENU;
    drawMenu();
}

static void initUpdatesCursor() {
    String response;
    int code = httpGet("/chat/api/updates?session_token=" + session_token + "&since_ms=0&limit=1", response);
    if (code != 200) {
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        return;
    }
    last_seen_ms = doc["server_time_ms"].as<uint64_t>();
    clock_offset_ms = (int64_t)last_seen_ms - (int64_t)millis();
    clock_valid = true;
    Serial.printf("updates cursor: %llu\n", (unsigned long long)last_seen_ms);
}

static void pollUpdates() {
    if (session_token.length() == 0) {
        return;
    }
    String response;
    int code = httpGet("/chat/api/updates?session_token=" + session_token +
                           "&since_ms=" + String((unsigned long long)last_seen_ms) + "&limit=10",
                       response);
    if (code != 200) {
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        return;
    }
    uint64_t server_now = doc["server_time_ms"].as<uint64_t>();
    if (server_now > 0) {
        clock_offset_ms = (int64_t)server_now - (int64_t)millis();
        clock_valid = true;
    }
    JsonArray items = doc["items"].as<JsonArray>();
    if (items.isNull() || items.size() == 0) {
        return;
    }

    bool notify_here = false;
    for (JsonObject item : items) {
        uint64_t ts = item["created_at_ms"].as<uint64_t>();
        if (ts > last_seen_ms) {
            last_seen_ms = ts;
        }
        long chat_id = item["chat_id"].as<long>();
        bool in_open_chat = (chat_id == current_chat_id) &&
                            (screen == Screen::CHAT_VIEW || screen == Screen::CHAT_INPUT);
        if (!in_open_chat) {
            notify_here = true;
        }
    }

    if (notify_here) {
        Serial.printf("updates: %d new\n", (int)items.size());
        if (setting_notify) {
            M5Cardputer.Speaker.tone(1800, 120);
        }
        if (screen_off) {
            screen_off = false;
            M5Cardputer.Display.setBrightness(BRIGHT_LEVELS[setting_bright]);
        }
        last_activity_ms = millis();
    }
}

// --- chat ---

static const uint16_t COL_BG = 0x0861;
static const uint16_t COL_HEADER = 0x10C3;
static const uint16_t COL_ACCENT = 0x07FF;
static const uint16_t COL_SEL = 0x1C9F;
static const uint16_t COL_CARD = 0x18E3;
static const uint16_t COL_TEXT = 0xEF5D;
static const uint16_t COL_DIM = 0x7BEF;

static const uint16_t AUTHOR_COLORS[] = {0x07FF, 0xFD20, 0x07E0, 0xF81F, 0xFFE0, 0x5D9F};

static uint16_t authorColor(const String &name) {
    uint16_t h = 0;
    for (size_t i = 0; i < name.length(); i++) {
        h = h * 31 + (uint8_t)name[i];
    }
    return AUTHOR_COLORS[h % (sizeof(AUTHOR_COLORS) / sizeof(AUTHOR_COLORS[0]))];
}

static String formatTimeMs(uint64_t ms) {
    if (ms == 0 || !clock_valid) {
        return "";
    }
    int64_t local_ms = (int64_t)ms + (int64_t)setting_tz * 3600000LL;
    time_t t = (time_t)(local_ms / 1000);
    struct tm tm_info;
    gmtime_r(&t, &tm_info);
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", tm_info.tm_hour, tm_info.tm_min);
    return String(buf);
}

static void drawBatteryIcon(int x, int y, int pct) {
    auto &d = M5Cardputer.Display;
    uint16_t color = pct < 0 ? COL_DIM : (pct > 20 ? 0x07E0 : 0xF800);
    d.drawRect(x, y, 18, 9, COL_TEXT);
    d.fillRect(x + 18, y + 2, 2, 5, COL_TEXT);
    if (pct > 0) {
        int w = (pct > 100 ? 100 : pct) * 14 / 100;
        if (w < 2) {
            w = 2;
        }
        d.fillRect(x + 2, y + 2, w, 5, color);
    }
}

static void drawTopBar(const String &title) {
    auto &d = M5Cardputer.Display;
    d.fillRect(0, 0, 240, 18, COL_HEADER);
    d.fillRect(0, 18, 240, 1, COL_ACCENT);
    d.setTextColor(COL_ACCENT, COL_HEADER);
    d.setCursor(6, 3);
    d.print(clip(title, 20));

    drawBatteryIcon(240 - 22, 4, (int)M5Cardputer.Power.getBatteryLevel());
    String clk = formatClock();
    if (clk.length() > 0) {
        d.setTextColor(COL_TEXT, COL_HEADER);
        d.setCursor(240 - 30 - (int)clk.length() * 6, 3);
        d.print(clk);
    }
}

static void drawHint(const String &text) {
    auto &d = M5Cardputer.Display;
    d.fillRect(0, 122, 240, 13, COL_HEADER);
    d.setTextColor(COL_DIM, COL_HEADER);
    d.setCursor(6, 122);
    d.print(clip(text, 38));
}

static void drawCardRow(int y, const String &left, const String &right, bool sel, uint16_t leftColor) {
    auto &d = M5Cardputer.Display;
    uint16_t bg = sel ? COL_SEL : COL_CARD;
    d.fillRoundRect(2, y, 236, 17, 3, bg);
    if (sel) {
        d.fillRoundRect(2, y, 6, 17, 3, COL_ACCENT);
    }
    d.setTextColor(leftColor, bg);
    d.setCursor(12, y + 4);
    d.print(left);
    if (right.length() > 0) {
        d.setTextColor(sel ? COL_TEXT : COL_DIM, bg);
        d.setCursor(238 - 6 - (int)right.length() * 6, y + 4);
        d.print(right);
    }
}

static void drawChatList() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(String("Чаты (") + chat_count + ")");

    int y = 22;
    for (int i = 0; i < chat_count && i < 5; i++) {
        bool sel = (i == chat_sel);
        drawCardRow(y, clip(chats[i].title, 24), "", sel, sel ? TFT_WHITE : COL_TEXT);
        y += 20;
    }
    if (chat_count == 0) {
        d.setTextColor(COL_DIM, COL_BG);
        d.setCursor(8, 50);
        d.print("Чатов пока нет");
    }

    drawHint("↑↓ move  →/Enter open  Esc back");
}

static void drawChatView() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(String("#") + clip(current_chat_title, 16));

    const int visible = 7;
    int end = msg_count - msg_scroll;
    int start = end - visible;
    if (start < 0) {
        start = 0;
    }
    if (end > msg_count) {
        end = msg_count;
    }

    int y = 23;
    for (int i = start; i < end && y < 104; i++) {
        bool mine = (msgs[i].author == session_login);
        uint16_t bg = mine ? COL_CARD : COL_BG;
        if (mine) {
            d.fillRoundRect(2, y - 3, 236, 15, 3, COL_CARD);
        }
        d.setTextColor(authorColor(msgs[i].author), bg);
        d.setCursor(6, y);
        d.print(clip(msgs[i].author, 9));
        d.setCursor(66, y);
        if (msgs[i].text.length() > 0) {
            d.setTextColor(COL_TEXT, bg);
            d.print(clip(msgs[i].text, 28));
        } else if (msgs[i].file.length() > 0) {
            d.setTextColor(TFT_YELLOW, bg);
            d.print(clip("[файл] " + msgs[i].file, 28));
        }
        y += 14;
        if (msgs[i].file.length() > 0 && msgs[i].text.length() > 0 && y < 104) {
            d.setTextColor(TFT_YELLOW, bg);
            d.setCursor(66, y);
            d.print(clip("[файл] " + msgs[i].file, 28));
            y += 14;
        }
    }

    d.fillRect(0, 108, 240, 27, COL_HEADER);
    d.fillRect(0, 108, 240, 1, COL_ACCENT);
    d.setTextColor(COL_TEXT, COL_HEADER);
    d.setCursor(6, 112);
    if (screen == Screen::CHAT_INPUT) {
        d.printf("> %s_", clip(input_text, 34).c_str());
    } else {
        d.printf("%d/%d  ↑↓ scroll  → write", msg_count - msg_scroll, msg_count);
    }
    d.setTextColor(COL_DIM, COL_HEADER);
    d.setCursor(6, 124);
    d.print("Esc back    Fn+↑↓ page");
}

static void drawMenu() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(String("Local Chat   ") + session_login);

    int y = 24;
    for (int i = 0; i < MENU_ITEMS; i++) {
        bool sel = (i == menu_sel);
        drawCardRow(y, String(sel ? "▶ " : "   ") + menu_titles[i], "", sel,
                    sel ? TFT_WHITE : COL_TEXT);
        y += 19;
    }

    drawHint("↑↓ move   →/Enter open");
}

static void buildAbout() {
    about_lines.clear();
    char buf[96];

    about_lines.push_back("Local Chat — локальный");
    about_lines.push_back("чат-сервер на Raspberry Pi 5.");
    about_lines.push_back("Работает без интернета:");
    about_lines.push_back("Wi-Fi и данные только внутри");
    about_lines.push_back("локальной сети.");
    about_lines.push_back("");
    about_lines.push_back("— Это устройство —");
    about_lines.push_back(String("  ") + device_name);
    about_lines.push_back(String("  id: ") + device_id);
    about_lines.push_back(String("  прошивка: v") + FW_VERSION);
    snprintf(buf, sizeof(buf), "  память: %lu КБ", (unsigned long)(ESP.getFreeHeap() / 1024));
    about_lines.push_back(buf);
    int lvl = (int)M5Cardputer.Power.getBatteryLevel();
    snprintf(buf, sizeof(buf), "  батарея: %d%%", lvl);
    about_lines.push_back(buf);
    about_lines.push_back("");
    about_lines.push_back("— Связь —");
    about_lines.push_back(String("  сеть: local-chat"));
    snprintf(buf, sizeof(buf), "  IP: %s", WiFi.localIP().toString().c_str());
    about_lines.push_back(buf);
    snprintf(buf, sizeof(buf), "  сигнал: %d dBm", (int)WiFi.RSSI());
    about_lines.push_back(buf);
    about_lines.push_back(String("  сервер: ") + SERVER_BASE);
    about_lines.push_back("");
    about_lines.push_back("— Аккаунт —");
    about_lines.push_back(String("  пользователь: ") + session_login);
    about_lines.push_back("");
    about_lines.push_back("— Безопасность —");
    about_lines.push_back("Сопряжение по 6-значному коду.");
    about_lines.push_back("Вход по HMAC-подписи: секрет");
    about_lines.push_back("устройства не передаётся по сети.");
    about_lines.push_back("Отвязка — в веб-интерфейсе.");
    about_lines.push_back("");
    about_lines.push_back("— Управление —");
    about_lines.push_back("; . , / — стрелки");
    about_lines.push_back("Enter — выбор / отправить");
    about_lines.push_back("Esc (`) — назад");
    about_lines.push_back("Fn+Enter / Fn+Space — страницы");
    about_lines.push_back("Fn+R — обновить");
    about_lines.push_back("");
    about_lines.push_back(String("сборка: ") + __DATE__);
}

static void drawAbout() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar("О проекте");

    int total = (int)about_lines.size();
    int visible = 7;
    int max_scroll = total > visible ? total - visible : 0;
    if (about_scroll > max_scroll) {
        about_scroll = max_scroll;
    }
    int y = 24;
    for (int i = about_scroll; i < total && y < 118; i++) {
        uint16_t color = COL_TEXT;
        if (about_lines[i].startsWith("—")) {
            color = COL_ACCENT;
        } else if (about_lines[i].startsWith("  ")) {
            color = COL_DIM;
        }
        d.setTextColor(color, COL_BG);
        d.setCursor(8, y);
        d.print(about_lines[i]);
        y += 13;
    }

    drawHint(String("↑↓ scroll  ") + about_scroll + "/" + max_scroll + "  Esc back");
}

static void drawBlogList() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(String("Блог (") + blog_count + ")");

    int y = 23;
    for (int i = 0; i < blog_count && i < 5; i++) {
        bool sel = (i == blog_sel);
        drawCardRow(y, clip(blog[i].title, 30), "", sel, sel ? TFT_WHITE : COL_TEXT);
        y += 19;
    }
    if (blog_count == 0) {
        d.setTextColor(COL_DIM, COL_BG);
        d.setCursor(8, 50);
        d.print("Постов пока нет");
    }

    drawHint("↑↓ move  →/Enter open  Esc back");
}

static void drawBlogView() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(clip(post_title, 20));

    int total = (int)post_lines.size();
    int visible = 7;
    int max_scroll = total > visible ? total - visible : 0;
    if (post_scroll > max_scroll) {
        post_scroll = max_scroll;
    }
    int y = 24;
    for (int i = post_scroll; i < total && y < 118; i++) {
        d.setTextColor(COL_TEXT, COL_BG);
        d.setCursor(8, y);
        d.print(post_lines[i]);
        y += 13;
    }

    drawHint(String("↑↓ scroll  ") + post_scroll + "/" + max_scroll + "  Esc back");
}

static void wrapPost(const String &text, int width) {
    post_lines.clear();
    String line;
    int last_space = -1;
    for (size_t i = 0; i < text.length(); i++) {
        char c = text[i];
        if (c == '\r') {
            continue;
        }
        if (c == '\n') {
            post_lines.push_back(line);
            line = "";
            last_space = -1;
            continue;
        }
        line += c;
        if (c == ' ') {
            last_space = (int)line.length() - 1;
        }
        if ((int)line.length() >= width) {
            if (last_space > 0 && last_space < (int)line.length() - 1) {
                String rest = line.substring(last_space + 1);
                line = line.substring(0, last_space);
                post_lines.push_back(line);
                line = rest;
            } else {
                post_lines.push_back(line);
                line = "";
            }
            last_space = -1;
        }
    }
    if (line.length() > 0) {
        post_lines.push_back(line);
    }
}

static void loadBlog() {
    String response;
    int code = httpGet("/blog/api/posts?session_token=" + session_token + "&limit=16&offset=0", response);
    if (code != 200) {
        net_status = String("blog err ") + code;
        Serial.printf("loadBlog: HTTP %d\n", code);
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        net_status = "blog json";
        return;
    }
    blog_count = 0;
    for (JsonObject item : doc["items"].as<JsonArray>()) {
        if (blog_count >= MAX_BLOG) {
            break;
        }
        blog[blog_count].id = item["post_id"].as<long>();
        blog[blog_count].title = String((const char *)(item["title"] | "?"));
        blog_count++;
    }
    if (blog_sel >= blog_count) {
        blog_sel = 0;
    }
    net_status = String("blog: ") + blog_count;
    Serial.printf("loadBlog: %d posts\n", blog_count);
}

static void openPost(int index) {
    if (index < 0 || index >= blog_count) {
        return;
    }
    String response;
    int code = httpGet("/blog/api/posts/" + String(blog[index].id) +
                           "?session_token=" + session_token,
                       response);
    if (code != 200) {
        net_status = String("post err ") + code;
        drawBlogList();
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        net_status = "post json";
        drawBlogList();
        return;
    }
    post_title = String((const char *)(doc["post"]["title"] | "?"));
    String body = String((const char *)(doc["post"]["body_text"] | ""));
    wrapPost(body, 40);
    post_scroll = 0;
    screen = Screen::BLOG_VIEW;
    Serial.printf("openPost: %ld lines=%d\n", blog[index].id, (int)post_lines.size());
    drawBlogView();
}

static void drawSupportList() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(String("Поддержка (") + ticket_count + ")");

    int y = 23;
    for (int i = 0; i < ticket_count && i < 5; i++) {
        bool sel = (i == ticket_sel);
        bool closed = tickets[i].status == "closed" || tickets[i].status == "resolved";
        String left = String(closed ? "○ " : "● ") + clip(tickets[i].title, 26);
        drawCardRow(y, left, "", sel, sel ? TFT_WHITE : (closed ? COL_DIM : TFT_GREEN));
        y += 19;
    }
    if (ticket_count == 0) {
        d.setTextColor(COL_DIM, COL_BG);
        d.setCursor(8, 50);
        d.print("Обращений пока нет");
    }

    drawHint("↑↓ move  → open  Fn+N new  Esc");
}

static void drawSupportView() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(String("#") + clip(current_ticket_title, 18));

    const int visible = 7;
    int end = msg_count - msg_scroll;
    int start = end - visible;
    if (start < 0) {
        start = 0;
    }
    if (end > msg_count) {
        end = msg_count;
    }

    int y = 23;
    for (int i = start; i < end && y < 104; i++) {
        d.setTextColor(COL_ACCENT, COL_BG);
        d.setCursor(6, y);
        d.print(clip(msgs[i].author, 9));
        d.setCursor(66, y);
        if (msgs[i].text.length() > 0) {
            d.setTextColor(COL_TEXT, COL_BG);
            d.print(clip(msgs[i].text, 28));
        } else if (msgs[i].file.length() > 0) {
            d.setTextColor(TFT_YELLOW, COL_BG);
            d.print(clip("[файл] " + msgs[i].file, 28));
        }
        y += 14;
        if (msgs[i].file.length() > 0 && msgs[i].text.length() > 0 && y < 104) {
            d.setTextColor(TFT_YELLOW, COL_BG);
            d.setCursor(66, y);
            d.print(clip("[файл] " + msgs[i].file, 28));
            y += 14;
        }
    }

    d.fillRect(0, 108, 240, 27, COL_HEADER);
    d.fillRect(0, 108, 240, 1, COL_ACCENT);
    d.setTextColor(COL_TEXT, COL_HEADER);
    d.setCursor(6, 112);
    if (screen == Screen::SUPPORT_INPUT) {
        d.printf("> %s_", clip(input_text, 34).c_str());
    } else {
        d.printf("%d/%d  ↑↓ scroll  → write", msg_count - msg_scroll, msg_count);
    }
    d.setTextColor(COL_DIM, COL_HEADER);
    d.setCursor(6, 124);
    d.print("Esc back    Fn+↑↓ page");
}

static void loadTickets() {
    String response;
    int code = httpGet("/support/api/tickets?session_token=" + session_token + "&limit=12&offset=0", response);
    if (code != 200) {
        net_status = String("tickets err ") + code;
        Serial.printf("loadTickets: HTTP %d\n", code);
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        net_status = "tickets json";
        return;
    }
    ticket_count = 0;
    for (JsonObject item : doc["items"].as<JsonArray>()) {
        if (ticket_count >= MAX_TICKETS) {
            break;
        }
        tickets[ticket_count].id = item["ticket_id"].as<long>();
        tickets[ticket_count].title = String((const char *)(item["title"] | "?"));
        tickets[ticket_count].status = String((const char *)(item["status"] | "open"));
        ticket_count++;
    }
    if (ticket_sel >= ticket_count) {
        ticket_sel = 0;
    }
    net_status = String("tickets: ") + ticket_count;
    Serial.printf("loadTickets: %d\n", ticket_count);
}

static void openTicket(int index) {
    if (index < 0 || index >= ticket_count) {
        return;
    }
    current_ticket_id = tickets[index].id;
    current_ticket_title = tickets[index].title;

    String response;
    int code = httpGet("/support/api/tickets/" + String(current_ticket_id) +
                           "/messages?session_token=" + session_token + "&limit=40&offset=0",
                       response);
    if (code != 200) {
        net_status = String("ticket err ") + code;
        drawSupportList();
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        net_status = "ticket json";
        return;
    }
    msg_count = 0;
    for (JsonObject item : doc["items"].as<JsonArray>()) {
        if (msg_count >= MAX_MSGS) {
            break;
        }
        msgs[msg_count].id = item["message_id"].as<long>();
        msgs[msg_count].author = String("#") + String(item["author_user_id"].as<long>());
        msgs[msg_count].text = String((const char *)(item["body_text"] | ""));
        msgs[msg_count].file = "";
        JsonArray atts = item["attachments"].as<JsonArray>();
        if (!atts.isNull() && atts.size() > 0) {
            msgs[msg_count].file = String((const char *)(atts[0]["filename"] | "file"));
        }
        msg_count++;
    }
    msg_scroll = 0;
    input_text = "";
    screen = Screen::SUPPORT_VIEW;
    Serial.printf("openTicket: %ld msgs=%d\n", current_ticket_id, msg_count);
    drawSupportView();
}

static void sendSupportMessage() {
    if (input_text.length() == 0) {
        screen = Screen::SUPPORT_VIEW;
        drawSupportView();
        return;
    }
    String text = input_text;
    input_text = "";
    String body = String("{\"session_token\":\"") + session_token +
                  "\",\"body_text\":\"" + escapeJson(text) + "\"}";
    String response;
    int code = httpPostJson("/support/api/tickets/" + String(current_ticket_id) + "/messages", body, response);
    Serial.printf("support send: HTTP %d\n", code);
    if (code == 200) {
        net_status = "sent";
        openTicket(ticket_sel);
    } else {
        net_status = String("send err ") + code;
        screen = Screen::SUPPORT_VIEW;
        drawSupportView();
    }
}

static void createSupportTicket() {
    if (input_text.length() == 0) {
        screen = Screen::SUPPORT_LIST;
        drawSupportList();
        return;
    }
    String text = input_text;
    input_text = "";
    String title = clip(text, 30);
    String body = String("{\"session_token\":\"") + session_token +
                  "\",\"title\":\"" + escapeJson(title) +
                  "\",\"body_text\":\"" + escapeJson(text) +
                  "\",\"kind\":\"support\"}";
    String response;
    int code = httpPostJson("/support/api/tickets", body, response);
    Serial.printf("ticket create: HTTP %d %s\n", code, response.substring(0, 100).c_str());
    loadTickets();
    screen = Screen::SUPPORT_LIST;
    drawSupportList();
}

static void drawSupportNew() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar("Новое обращение");

    d.setTextColor(COL_TEXT, COL_BG);
    d.setCursor(8, 40);
    d.print("Опиши проблему текстом.");
    d.setCursor(8, 56);
    d.print("Enter — отправить, Esc — отмена.");
    d.setTextColor(COL_DIM, COL_BG);
    d.setCursor(8, 76);
    d.print("(заголовок создастся сам)");

    d.fillRect(0, 108, 240, 27, COL_HEADER);
    d.fillRect(0, 108, 240, 1, COL_ACCENT);
    d.setTextColor(COL_TEXT, COL_HEADER);
    d.setCursor(6, 118);
    d.printf("> %s_", clip(input_text, 34).c_str());
}

static void applyLed() {
    if (!M5.Led.isEnabled()) {
        return;
    }
    if (setting_led) {
        M5.Led.setAllColor(LED_COLORS[setting_led_color][0],
                           LED_COLORS[setting_led_color][1],
                           LED_COLORS[setting_led_color][2]);
    } else {
        M5.Led.setAllColor(0, 0, 0);
    }
}

static void applySound() {
    M5Cardputer.Speaker.setVolume(setting_sound ? VOLUME_LEVELS[setting_volume] : 0);
}

static void applyWifiSleep() {
    if (WiFi.status() == WL_CONNECTED) {
        WiFi.setSleep(setting_wifi_sleep);
    }
}

static String formatClock() {
    if (!setting_clock || !clock_valid) {
        return "";
    }
    int64_t now_ms = (int64_t)millis() + clock_offset_ms + (int64_t)setting_tz * 3600000LL;
    time_t t = (time_t)(now_ms / 1000);
    struct tm tm_info;
    gmtime_r(&t, &tm_info);
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", tm_info.tm_hour, tm_info.tm_min);
    return String(buf);
}

static void resetSettings() {
    setting_bright = 3;
    setting_sound = true;
    setting_volume = 1;
    setting_sleep = 0;
    setting_notify = true;
    setting_led = false;
    setting_led_color = 0;
    setting_clock = true;
    setting_tz = 3;
    setting_wifi_sleep = false;
    prefs.putInt("bright", setting_bright);
    prefs.putBool("sound", setting_sound);
    prefs.putInt("volume", setting_volume);
    prefs.putInt("sleep", setting_sleep);
    prefs.putBool("notify", setting_notify);
    prefs.putBool("led", setting_led);
    prefs.putInt("led_color", setting_led_color);
    prefs.putBool("clock", setting_clock);
    prefs.putInt("tz", setting_tz);
    prefs.putBool("wifi_sleep", setting_wifi_sleep);
    M5Cardputer.Display.setBrightness(BRIGHT_LEVELS[setting_bright]);
    applySound();
    applyLed();
    applyWifiSleep();
}

static void settingsAdjustScroll() {
    if (settings_sel < settings_scroll) {
        settings_scroll = settings_sel;
    }
    if (settings_sel >= settings_scroll + SETTINGS_VISIBLE) {
        settings_scroll = settings_sel - SETTINGS_VISIBLE + 1;
    }
    if (settings_scroll < 0) {
        settings_scroll = 0;
    }
    if (settings_scroll > SETTINGS_COUNT - SETTINGS_VISIBLE) {
        settings_scroll = SETTINGS_COUNT - SETTINGS_VISIBLE;
    }
}

static String settingValueText(int id) {
    switch (id) {
        case SET_BRIGHT:
            return BRIGHT_LABELS[setting_bright];
        case SET_SOUND:
            return setting_sound ? "Вкл" : "Выкл";
        case SET_VOLUME:
            return VOLUME_LABELS[setting_volume];
        case SET_SLEEP:
            return SLEEP_LABELS[setting_sleep];
        case SET_NOTIFY:
            return setting_notify ? "Вкл" : "Выкл";
        case SET_LED:
            return setting_led ? "Вкл" : "Выкл";
        case SET_LED_COLOR:
            return LED_COLOR_LABELS[setting_led_color];
        case SET_CLOCK:
            return setting_clock ? "Вкл" : "Выкл";
        case SET_TZ: {
            char buf[12];
            snprintf(buf, sizeof(buf), "UTC%+d", setting_tz);
            return String(buf);
        }
        case SET_WIFI_SLEEP:
            return setting_wifi_sleep ? "Вкл" : "Выкл";
        case SET_RESET:
            return "Enter";
        case SET_REBOOT:
            return "Enter";
    }
    return "";
}

static void drawSettings() {
    auto &d = M5Cardputer.Display;
    d.fillScreen(COL_BG);
    d.setTextSize(1);

    drawTopBar(String("Настройки ") + (settings_sel + 1) + "/" + SETTINGS_COUNT);

    int y = 23;
    for (int row = 0; row < SETTINGS_VISIBLE; row++) {
        int index = settings_scroll + row;
        if (index >= SETTINGS_COUNT) {
            break;
        }
        int id = SETTINGS_ORDER[index];
        bool sel = (index == settings_sel);
        drawCardRow(y, SETTINGS_LABELS[id], settingValueText(id), sel,
                    sel ? TFT_WHITE : COL_TEXT);
        y += 19;
    }

    drawHint("↑↓ move  ←→ change  Enter ok  Esc");
}

static void drawScreen() {
    switch (screen) {
        case Screen::PAIR:
            drawPairScreen();
            break;
        case Screen::MENU:
            drawMenu();
            break;
        case Screen::CHAT_LIST:
            drawChatList();
            break;
        case Screen::CHAT_VIEW:
        case Screen::CHAT_INPUT:
            drawChatView();
            break;
        case Screen::BLOG_LIST:
            drawBlogList();
            break;
        case Screen::BLOG_VIEW:
            drawBlogView();
            break;
        case Screen::SUPPORT_LIST:
            drawSupportList();
            break;
        case Screen::SUPPORT_VIEW:
        case Screen::SUPPORT_INPUT:
            drawSupportView();
            break;
        case Screen::SUPPORT_NEW:
            drawSupportNew();
            break;
        case Screen::SETTINGS:
            drawSettings();
            break;
        case Screen::ABOUT:
            drawAbout();
            break;
    }
}

static bool loadChats() {
    String response;
    int code = httpGet("/chat/api/chats?session_token=" + session_token, response);
    if (code != 200) {
        net_status = String("chats err ") + code;
        Serial.printf("loadChats: HTTP %d\n", code);
        return false;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        net_status = "chats json";
        return false;
    }
    chat_count = 0;
    for (JsonObject item : doc["items"].as<JsonArray>()) {
        if (chat_count >= MAX_CHATS) {
            break;
        }
        chats[chat_count].id = item["chat_id"].as<long>();
        chats[chat_count].title = String((const char *)(item["title"] | "?"));
        chat_count++;
    }
    if (chat_sel >= chat_count) {
        chat_sel = 0;
    }
    net_status = String("chats: ") + chat_count;
    Serial.printf("loadChats: %d chats\n", chat_count);
    return true;
}

static bool loadMessages(long chat_id, int limit) {
    String response;
    int code = httpGet("/chat/api/chats/" + String(chat_id) +
                           "/messages?session_token=" + session_token +
                           "&limit=" + String(limit) + "&offset=0",
                       response);
    if (code != 200) {
        net_status = String("msgs err ") + code;
        Serial.printf("loadMessages: HTTP %d\n", code);
        return false;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        net_status = "msgs json";
        return false;
    }
    msg_count = 0;
    last_msg_id = 0;
    for (JsonObject item : doc["items"].as<JsonArray>()) {
        if (msg_count >= MAX_MSGS) {
            break;
        }
        msgs[msg_count].id = item["message_id"].as<long>();
        msgs[msg_count].author = String((const char *)(item["author_login"] | "?"));
        msgs[msg_count].text = String((const char *)(item["body_text"] | ""));
        msgs[msg_count].file = "";
        JsonArray atts = item["attachments"].as<JsonArray>();
        if (!atts.isNull() && atts.size() > 0) {
            msgs[msg_count].file = String((const char *)(atts[0]["filename"] | "file"));
            if (atts.size() > 1) {
                msgs[msg_count].file += " +" + String(atts.size() - 1);
            }
        }
        if (msgs[msg_count].id > last_msg_id) {
            last_msg_id = msgs[msg_count].id;
        }
        msg_count++;
    }
    msg_scroll = 0;
    net_status = String("msgs: ") + msg_count;
    Serial.printf("loadMessages: %d messages, last_id=%ld\n", msg_count, last_msg_id);
    return true;
}

static void openChat(int index) {
    if (index < 0 || index >= chat_count) {
        return;
    }
    current_chat_id = chats[index].id;
    current_chat_title = chats[index].title;
    input_text = "";
    screen = Screen::CHAT_VIEW;
    loadMessages(current_chat_id, 40);
    drawChatView();
}

static void sendCurrentMessage() {
    if (input_text.length() == 0) {
        screen = Screen::CHAT_VIEW;
        drawChatView();
        return;
    }
    String text = input_text;
    input_text = "";
    String body = String("{\"session_token\":\"") + session_token +
                  "\",\"body_text\":\"" + escapeJson(text) + "\"}";
    String response;
    int code = httpPostJson("/chat/api/chats/" + String(current_chat_id) + "/messages", body, response);
    Serial.printf("send: HTTP %d %s\n", code, response.substring(0, 120).c_str());
    if (code == 200) {
        net_status = "sent";
        loadMessages(current_chat_id, 40);
    } else {
        net_status = String("send err ") + code;
    }
    screen = Screen::CHAT_VIEW;
    drawChatView();
}

static void pollNewMessages() {
    if (current_chat_id == 0 || session_token.length() == 0) {
        return;
    }
    String response;
    int code = httpGet("/chat/api/chats/" + String(current_chat_id) +
                           "/messages?session_token=" + session_token + "&limit=10&offset=0",
                       response);
    if (code != 200) {
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, response)) {
        return;
    }
    bool added = false;
    int added_count = 0;
    for (JsonObject item : doc["items"].as<JsonArray>()) {
        long id = item["message_id"].as<long>();
        if (id <= last_msg_id) {
            continue;
        }
        if (msg_count >= MAX_MSGS) {
            for (int i = 1; i < MAX_MSGS; i++) {
                msgs[i - 1] = msgs[i];
            }
            msg_count = MAX_MSGS - 1;
        }
        msgs[msg_count].id = id;
        msgs[msg_count].author = String((const char *)(item["author_login"] | "?"));
        msgs[msg_count].text = String((const char *)(item["body_text"] | ""));
        msgs[msg_count].file = "";
        JsonArray atts = item["attachments"].as<JsonArray>();
        if (!atts.isNull() && atts.size() > 0) {
            msgs[msg_count].file = String((const char *)(atts[0]["filename"] | "file"));
            if (atts.size() > 1) {
                msgs[msg_count].file += " +" + String(atts.size() - 1);
            }
        }
        msg_count++;
        last_msg_id = id;
        added = true;
        added_count++;
    }
    if (added) {
        Serial.printf("poll: +%d new, last_id=%ld\n", added_count, last_msg_id);
        if (setting_notify) {
            M5Cardputer.Speaker.tone(1800, 60);
        }
        if (screen_off) {
            screen_off = false;
            M5Cardputer.Display.setBrightness(BRIGHT_LEVELS[setting_bright]);
        }
        last_activity_ms = millis();
        if (msg_scroll == 0 && screen != Screen::CHAT_INPUT) {
            drawChatView();
        }
    }
}

struct KeyInfo {
    bool up = false;
    bool down = false;
    bool left = false;
    bool right = false;
    bool esc = false;
    bool page_up = false;
    bool page_down = false;
    bool enter = false;
    bool del = false;
    bool opt = false;
    bool space = false;
    bool reload = false;
    bool fn_n = false;
    String chars;
};

static KeyInfo readKeys(const Keyboard_Class::KeysState &st) {
    KeyInfo k;
    bool nav_mode = (screen != Screen::CHAT_INPUT && screen != Screen::SUPPORT_INPUT &&
                     screen != Screen::SUPPORT_NEW);
    k.enter = st.enter && !st.fn;
    k.del = st.del && !st.fn;
    k.opt = st.opt;
    k.page_up = st.enter && st.fn;
    k.page_down = st.space && st.fn;
    k.space = st.space && !st.fn;

    for (auto c : st.word) {
        if ((st.fn || nav_mode) && c == ';') {
            k.up = true;
            continue;
        }
        if ((st.fn || nav_mode) && c == '.') {
            k.down = true;
            continue;
        }
        if ((st.fn || nav_mode) && c == ',') {
            k.right = true;
            continue;
        }
        if ((st.fn || nav_mode) && c == '/') {
            k.left = true;
            continue;
        }
        if (st.fn && c == 'r') {
            k.reload = true;
            continue;
        }
        if (st.fn && c == 'n') {
            k.fn_n = true;
            continue;
        }
        if (!st.fn && c == '`') {
            k.esc = true;
            continue;
        }
        if (!st.fn) {
            k.chars += c;
        }
    }
    return k;
}

static void handleKeys(const Keyboard_Class::KeysState &status) {
    KeyInfo k = readKeys(status);

    if (screen == Screen::MENU) {
        if (k.up) {
            menu_sel = (menu_sel > 0) ? menu_sel - 1 : MENU_ITEMS - 1;
            drawMenu();
            return;
        }
        if (k.down) {
            menu_sel = (menu_sel + 1) % MENU_ITEMS;
            drawMenu();
            return;
        }
        if (k.enter || k.right) {
            if (menu_sel == 0) {
                if (chat_count == 0) {
                    loadChats();
                }
                screen = Screen::CHAT_LIST;
                drawChatList();
            } else if (menu_sel == 1) {
                loadBlog();
                screen = Screen::BLOG_LIST;
                drawBlogList();
            } else if (menu_sel == 2) {
                loadTickets();
                screen = Screen::SUPPORT_LIST;
                drawSupportList();
            } else if (menu_sel == 3) {
                settings_sel = 0;
                screen = Screen::SETTINGS;
                drawSettings();
            } else {
                buildAbout();
                about_scroll = 0;
                screen = Screen::ABOUT;
                drawAbout();
            }
            return;
        }
        return;
    }

    if (screen == Screen::SUPPORT_LIST) {
        if (k.up) {
            if (ticket_count > 0) {
                ticket_sel = (ticket_sel > 0) ? ticket_sel - 1 : ticket_count - 1;
            }
            drawSupportList();
            return;
        }
        if (k.down) {
            if (ticket_count > 0) {
                ticket_sel = (ticket_sel + 1) % ticket_count;
            }
            drawSupportList();
            return;
        }
        if (k.enter || k.right) {
            openTicket(ticket_sel);
            return;
        }
        if (k.esc || k.opt || k.left) {
            screen = Screen::MENU;
            drawMenu();
            return;
        }
        if (k.reload) {
            loadTickets();
            drawSupportList();
            return;
        }
        if (k.fn_n) {
            input_text = "";
            screen = Screen::SUPPORT_NEW;
            drawSupportNew();
            return;
        }
        return;
    }

    if (screen == Screen::SUPPORT_VIEW) {
        if (k.enter || k.right) {
            screen = Screen::SUPPORT_INPUT;
            drawSupportView();
            return;
        }
        if (k.esc || k.opt || k.left) {
            loadTickets();
            screen = Screen::SUPPORT_LIST;
            drawSupportList();
            return;
        }
        if (k.up || k.page_up) {
            int step = k.page_up ? 8 : 1;
            msg_scroll += step;
            int max_scroll = msg_count > 0 ? msg_count - 1 : 0;
            if (msg_scroll > max_scroll) {
                msg_scroll = max_scroll;
            }
            drawSupportView();
            return;
        }
        if (k.down || k.page_down) {
            int step = k.page_down ? 8 : 1;
            msg_scroll -= step;
            if (msg_scroll < 0) {
                msg_scroll = 0;
            }
            drawSupportView();
            return;
        }
        return;
    }

    if (screen == Screen::SUPPORT_INPUT) {
        if (k.enter) {
            sendSupportMessage();
            return;
        }
        if (k.esc || k.opt || k.left) {
            input_text = "";
            screen = Screen::SUPPORT_VIEW;
            drawSupportView();
            return;
        }
        if (k.del) {
            if (input_text.length() > 0) {
                input_text.remove(input_text.length() - 1);
            }
            drawSupportView();
            return;
        }
        for (int i = 0; i < (int)k.chars.length(); i++) {
            if (input_text.length() < 180) {
                input_text += k.chars[i];
            }
        }
        if (k.space && input_text.length() < 180) {
            input_text += ' ';
        }
        drawSupportView();
        return;
    }

    if (screen == Screen::SUPPORT_NEW) {
        if (k.enter) {
            createSupportTicket();
            return;
        }
        if (k.esc || k.opt || k.left) {
            input_text = "";
            screen = Screen::SUPPORT_LIST;
            drawSupportList();
            return;
        }
        if (k.del) {
            if (input_text.length() > 0) {
                input_text.remove(input_text.length() - 1);
            }
            drawSupportNew();
            return;
        }
        for (int i = 0; i < (int)k.chars.length(); i++) {
            if (input_text.length() < 180) {
                input_text += k.chars[i];
            }
        }
        if (k.space && input_text.length() < 180) {
            input_text += ' ';
        }
        drawSupportNew();
        return;
    }

    if (screen == Screen::SETTINGS) {
        int id = SETTINGS_ORDER[settings_sel];
        if (k.up) {
            settings_sel = (settings_sel > 0) ? settings_sel - 1 : SETTINGS_COUNT - 1;
            settingsAdjustScroll();
            drawSettings();
            return;
        }
        if (k.down) {
            settings_sel = (settings_sel + 1) % SETTINGS_COUNT;
            settingsAdjustScroll();
            drawSettings();
            return;
        }
        if (k.enter) {
            if (id == SET_RESET) {
                resetSettings();
                drawSettings();
            } else if (id == SET_REBOOT) {
                Serial.println("reboot requested");
                delay(200);
                ESP.restart();
            }
            return;
        }
        if (k.left || k.right) {
            int dir = k.right ? 1 : -1;
            switch (id) {
                case SET_BRIGHT:
                    setting_bright += dir;
                    if (setting_bright < 0) {
                        setting_bright = 0;
                    }
                    if (setting_bright > 3) {
                        setting_bright = 3;
                    }
                    M5Cardputer.Display.setBrightness(BRIGHT_LEVELS[setting_bright]);
                    prefs.putInt("bright", setting_bright);
                    break;
                case SET_SOUND:
                    setting_sound = !setting_sound;
                    applySound();
                    prefs.putBool("sound", setting_sound);
                    if (setting_sound) {
                        M5Cardputer.Speaker.tone(1800, 80);
                    }
                    break;
                case SET_VOLUME:
                    setting_volume += dir;
                    if (setting_volume < 0) {
                        setting_volume = 0;
                    }
                    if (setting_volume > 4) {
                        setting_volume = 4;
                    }
                    applySound();
                    prefs.putInt("volume", setting_volume);
                    M5Cardputer.Speaker.tone(1800, 80);
                    break;
                case SET_SLEEP:
                    setting_sleep += dir;
                    if (setting_sleep < 0) {
                        setting_sleep = 0;
                    }
                    if (setting_sleep > 3) {
                        setting_sleep = 3;
                    }
                    prefs.putInt("sleep", setting_sleep);
                    break;
                case SET_NOTIFY:
                    setting_notify = !setting_notify;
                    prefs.putBool("notify", setting_notify);
                    break;
                case SET_LED:
                    setting_led = !setting_led;
                    applyLed();
                    prefs.putBool("led", setting_led);
                    break;
                case SET_LED_COLOR:
                    setting_led_color = (setting_led_color + dir + 6) % 6;
                    if (setting_led) {
                        applyLed();
                    }
                    prefs.putInt("led_color", setting_led_color);
                    break;
                case SET_CLOCK:
                    setting_clock = !setting_clock;
                    prefs.putBool("clock", setting_clock);
                    break;
                case SET_TZ:
                    setting_tz += dir;
                    if (setting_tz < -12) {
                        setting_tz = -12;
                    }
                    if (setting_tz > 14) {
                        setting_tz = 14;
                    }
                    prefs.putInt("tz", setting_tz);
                    break;
                case SET_WIFI_SLEEP:
                    setting_wifi_sleep = !setting_wifi_sleep;
                    applyWifiSleep();
                    prefs.putBool("wifi_sleep", setting_wifi_sleep);
                    break;
                default:
                    break;
            }
            drawSettings();
            return;
        }
        if (k.esc || k.opt) {
            screen = Screen::MENU;
            drawMenu();
            return;
        }
        return;
    }

    if (screen == Screen::ABOUT) {
        if (k.up || k.page_up) {
            about_scroll -= k.page_up ? 8 : 1;
            if (about_scroll < 0) {
                about_scroll = 0;
            }
            drawAbout();
            return;
        }
        if (k.down || k.page_down) {
            about_scroll += k.page_down ? 8 : 1;
            drawAbout();
            return;
        }
        if (k.esc || k.opt || k.left) {
            screen = Screen::MENU;
            drawMenu();
        }
        return;
    }

    if (screen == Screen::BLOG_LIST) {
        if (k.up) {
            if (blog_count > 0) {
                blog_sel = (blog_sel > 0) ? blog_sel - 1 : blog_count - 1;
            }
            drawBlogList();
            return;
        }
        if (k.down) {
            if (blog_count > 0) {
                blog_sel = (blog_sel + 1) % blog_count;
            }
            drawBlogList();
            return;
        }
        if (k.enter || k.right) {
            openPost(blog_sel);
            return;
        }
        if (k.esc || k.opt || k.left) {
            screen = Screen::MENU;
            drawMenu();
            return;
        }
        if (k.reload) {
            loadBlog();
            drawBlogList();
            return;
        }
        return;
    }

    if (screen == Screen::BLOG_VIEW) {
        if (k.up || k.page_up) {
            post_scroll -= k.page_up ? 8 : 1;
            if (post_scroll < 0) {
                post_scroll = 0;
            }
            drawBlogView();
            return;
        }
        if (k.down || k.page_down) {
            post_scroll += k.page_down ? 8 : 1;
            drawBlogView();
            return;
        }
        if (k.esc || k.opt || k.left) {
            screen = Screen::BLOG_LIST;
            drawBlogList();
            return;
        }
        return;
    }

    if (screen == Screen::CHAT_LIST) {
        if (k.enter || k.right) {
            openChat(chat_sel);
            return;
        }
        if (k.esc || k.opt || k.left) {
            screen = Screen::MENU;
            drawMenu();
            return;
        }
        if (k.reload) {
            loadChats();
            drawChatList();
            return;
        }
        if (k.up) {
            if (chat_count > 0) {
                chat_sel = (chat_sel > 0) ? chat_sel - 1 : chat_count - 1;
            }
            drawChatList();
            return;
        }
        if (k.down) {
            if (chat_count > 0) {
                chat_sel = (chat_sel + 1) % chat_count;
            }
            drawChatList();
            return;
        }
        return;
    }

    if (screen == Screen::CHAT_VIEW) {
        if (k.enter || k.right) {
            screen = Screen::CHAT_INPUT;
            drawChatView();
            return;
        }
        if (k.esc || k.opt || k.left) {
            screen = Screen::CHAT_LIST;
            drawChatList();
            return;
        }
        if (k.reload) {
            loadMessages(current_chat_id, 40);
            drawChatView();
            return;
        }
        if (k.up || k.page_up) {
            int step = k.page_up ? 8 : 1;
            msg_scroll += step;
            int max_scroll = msg_count > 0 ? msg_count - 1 : 0;
            if (msg_scroll > max_scroll) {
                msg_scroll = max_scroll;
            }
            drawChatView();
            return;
        }
        if (k.down || k.page_down) {
            int step = k.page_down ? 8 : 1;
            msg_scroll -= step;
            if (msg_scroll < 0) {
                msg_scroll = 0;
            }
            drawChatView();
            return;
        }
        return;
    }

    if (screen == Screen::CHAT_INPUT) {
        if (k.enter) {
            sendCurrentMessage();
            return;
        }
        if (k.esc || k.opt || k.left) {
            input_text = "";
            screen = Screen::CHAT_VIEW;
            drawChatView();
            return;
        }
        if (k.del) {
            if (input_text.length() > 0) {
                input_text.remove(input_text.length() - 1);
            }
            drawChatView();
            return;
        }
        for (int i = 0; i < (int)k.chars.length(); i++) {
            if (input_text.length() < 180) {
                input_text += k.chars[i];
            }
        }
        if (k.space && input_text.length() < 180) {
            input_text += ' ';
        }
        drawChatView();
        return;
    }
}

// --- arduino ---

void setup() {
    auto cfg = M5.config();
    M5Cardputer.begin(cfg, true);

    Serial.begin(115200);
    delay(300);

    M5Cardputer.Display.setRotation(1);
    bool font_ok = M5Cardputer.Display.loadFont(lc_font_10);
    Serial.printf("font loaded: %d\n", font_ok ? 1 : 0);
    drawPairScreen();

    Serial.println();
    Serial.println("=== LC CHAT ===");

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

    setting_bright = prefs.getInt("bright", 3);
    setting_sound = prefs.getBool("sound", true);
    setting_volume = prefs.getInt("volume", 1);
    setting_sleep = prefs.getInt("sleep", 0);
    setting_notify = prefs.getBool("notify", true);
    setting_led = prefs.getBool("led", false);
    setting_led_color = prefs.getInt("led_color", 0);
    setting_clock = prefs.getBool("clock", true);
    setting_tz = prefs.getInt("tz", 3);
    setting_wifi_sleep = prefs.getBool("wifi_sleep", false);
    if (setting_bright < 0 || setting_bright > 3) {
        setting_bright = 3;
    }
    if (setting_volume < 0 || setting_volume > 4) {
        setting_volume = 1;
    }
    if (setting_sleep < 0 || setting_sleep > 3) {
        setting_sleep = 0;
    }
    if (setting_led_color < 0 || setting_led_color > 5) {
        setting_led_color = 0;
    }
    if (setting_tz < -12 || setting_tz > 14) {
        setting_tz = 3;
    }
    M5Cardputer.Display.setBrightness(BRIGHT_LEVELS[setting_bright]);
    applySound();
    applyLed();

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
        last_activity_ms = millis();
        if (screen_off) {
            screen_off = false;
            M5Cardputer.Display.setBrightness(BRIGHT_LEVELS[setting_bright]);
        } else {
            Keyboard_Class::KeysState status = M5Cardputer.Keyboard.keysState();
            if (screen == Screen::PAIR) {
                if (status.enter) {
                    if (paired) {
                        runDeviceSession();
                    } else {
                        requestPairingCode();
                    }
                }
            } else {
                handleKeys(status);
            }
        }
    }

    if (setting_sleep > 0 && !screen_off &&
        millis() - last_activity_ms > (uint32_t)SLEEP_MS[setting_sleep]) {
        screen_off = true;
        M5Cardputer.Display.setBrightness(0);
    }

    static uint32_t last_pair_poll = 0;
    if (screen == Screen::PAIR && !paired && pairing_id.length() == 32 &&
        millis() - last_pair_poll > 2000) {
        last_pair_poll = millis();
        pollPairingStatus();
    }

    static uint32_t last_retry = 0;
    if (screen == Screen::PAIR && paired && session_token.length() == 0 &&
        millis() - last_retry > 15000) {
        last_retry = millis();
        runDeviceSession();
    }

    static uint32_t last_updates_poll = 0;
    if (session_token.length() > 0 && millis() - last_updates_poll > 8000) {
        last_updates_poll = millis();
        pollUpdates();
    }

    static uint32_t last_msg_poll = 0;
    if (screen != Screen::PAIR && session_token.length() > 0 &&
        millis() - last_msg_poll > MSG_POLL_MS) {
        last_msg_poll = millis();
        pollNewMessages();
    }

    static uint32_t last_alive = 0;
    if (millis() - last_alive > 5000) {
        last_alive = millis();
        Serial.printf("alive wifi=%d paired=%d session=%d screen=%d chat=%ld msgs=%d bat=%d heap=%lu\n",
                      WiFi.status() == WL_CONNECTED ? 1 : 0,
                      paired ? 1 : 0,
                      session_token.length() > 0 ? 1 : 0,
                      (int)screen,
                      current_chat_id,
                      msg_count,
                      (int)M5Cardputer.Power.getBatteryLevel(),
                      (unsigned long)ESP.getFreeHeap());
    }

    delay(10);
}
