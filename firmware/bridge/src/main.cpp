// LC Bridge — M5Stamp S3: ESP-NOW <-> USB CDC (Raspberry Pi).
//
// Devices (Cardputer) talk to the bridge over ESP-NOW; the bridge forwards
// their JSON requests to the RPi over USB serial, where a small daemon runs
// them against the local server and sends responses back.
//
// ESP-NOW frame:  [0x4C][type:1][frag_index:1][frag_count:1][payload <= 200]
//   type 0x01 request (device -> bridge), 0x02 response (bridge -> device),
//   0x03 ping, 0x04 pong
//
// USB frame:      [0xAA][type:1][len:2 LE][mac:6][payload:len]
//   type 0x01 request (bridge -> daemon), 0x02 response (daemon -> bridge),
//   0x03 hello (bridge -> daemon)

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

static const uint8_t USB_MAGIC = 0xAA;
static const uint8_t ESPNOW_MAGIC = 0x4C;
static const uint8_t CHANNEL = 1;
static const size_t FRAG_PAYLOAD = 200;
static const size_t RX_BUF = 8192;

static uint8_t usb_rx[RX_BUF];
static size_t usb_rx_len = 0;

static bool assembly_active = false;
static uint8_t assembly_mac[6];
static uint8_t assembly_next_frag = 0;
static uint8_t assembly_frag_count = 0;
static size_t assembly_len = 0;
static uint8_t assembly_data[RX_BUF];

static uint32_t rx_requests = 0;
static uint32_t tx_responses = 0;

static void send_usb_frame(uint8_t type, const uint8_t *mac, const uint8_t *data, size_t len) {
    uint8_t header[10];
    header[0] = USB_MAGIC;
    header[1] = type;
    header[2] = (uint8_t)(len & 0xFF);
    header[3] = (uint8_t)((len >> 8) & 0xFF);
    memcpy(header + 4, mac, 6);
    Serial.write(header, sizeof(header));
    if (len > 0 && data != nullptr) {
        Serial.write(data, len);
    }
}

static void ensure_peer(const uint8_t *mac) {
    if (esp_now_is_peer_exist(mac)) {
        return;
    }
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, mac, 6);
    peer.channel = CHANNEL;
    peer.encrypt = false;
    esp_now_add_peer(&peer);
}

static void send_espnow_fragments(uint8_t type, const uint8_t *mac, const uint8_t *data, size_t len) {
    ensure_peer(mac);
    uint8_t frag_count = (uint8_t)((len + FRAG_PAYLOAD - 1) / FRAG_PAYLOAD);
    if (frag_count == 0) {
        frag_count = 1;
    }
    for (uint8_t i = 0; i < frag_count; i++) {
        size_t offset = (size_t)i * FRAG_PAYLOAD;
        size_t chunk = len - offset;
        if (chunk > FRAG_PAYLOAD) {
            chunk = FRAG_PAYLOAD;
        }
        uint8_t frame[4 + FRAG_PAYLOAD];
        frame[0] = ESPNOW_MAGIC;
        frame[1] = type;
        frame[2] = i;
        frame[3] = frag_count;
        if (chunk > 0) {
            memcpy(frame + 4, data + offset, chunk);
        }
        esp_now_send(mac, frame, 4 + chunk);
        delay(4);
    }
}

static void on_espnow_recv(const uint8_t *mac, const uint8_t *data, int len) {
    if (len < 4 || data[0] != ESPNOW_MAGIC) {
        return;
    }
    uint8_t type = data[1];
    uint8_t frag_index = data[2];
    uint8_t frag_count = data[3];
    const uint8_t *payload = data + 4;
    size_t payload_len = (size_t)(len - 4);

    if (type == 0x03) {
        uint8_t pong[4] = {ESPNOW_MAGIC, 0x04, 0, 1};
        ensure_peer(mac);
        esp_now_send(mac, pong, sizeof(pong));
        return;
    }

    if (type != 0x01) {
        return;
    }

    if (frag_index == 0) {
        assembly_active = true;
        assembly_len = 0;
        assembly_next_frag = 0;
        assembly_frag_count = frag_count;
        memcpy(assembly_mac, mac, 6);
    }
    if (!assembly_active) {
        return;
    }
    if (frag_index != assembly_next_frag) {
        assembly_active = false;
        return;
    }
    if (assembly_len + payload_len <= RX_BUF) {
        memcpy(assembly_data + assembly_len, payload, payload_len);
        assembly_len += payload_len;
    }
    assembly_next_frag++;
    if ((uint8_t)(frag_index + 1) >= frag_count) {
        rx_requests++;
        send_usb_frame(0x01, assembly_mac, assembly_data, assembly_len);
        assembly_active = false;
    }
}

static void poll_usb() {
    while (Serial.available() > 0) {
        int b = Serial.read();
        if (b < 0) {
            break;
        }
        if (usb_rx_len < RX_BUF) {
            usb_rx[usb_rx_len++] = (uint8_t)b;
        } else {
            usb_rx_len = 0;
        }
    }

    while (usb_rx_len >= 10) {
        if (usb_rx[0] != USB_MAGIC) {
            size_t i = 1;
            while (i < usb_rx_len && usb_rx[i] != USB_MAGIC) {
                i++;
            }
            memmove(usb_rx, usb_rx + i, usb_rx_len - i);
            usb_rx_len -= i;
            continue;
        }
        uint16_t len = (uint16_t)usb_rx[2] | ((uint16_t)usb_rx[3] << 8);
        if (usb_rx_len < (size_t)10 + len) {
            break;
        }
        uint8_t type = usb_rx[1];
        uint8_t mac[6];
        memcpy(mac, usb_rx + 4, 6);
        if (type == 0x02 && len > 0) {
            tx_responses++;
            send_espnow_fragments(0x02, mac, usb_rx + 10, len);
        }
        size_t consumed = (size_t)10 + len;
        memmove(usb_rx, usb_rx + consumed, usb_rx_len - consumed);
        usb_rx_len -= consumed;
    }
}

void setup() {
    Serial.begin(115200);
    delay(300);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    esp_wifi_set_channel(CHANNEL, WIFI_SECOND_CHAN_NONE);

    if (esp_now_init() != ESP_OK) {
        Serial.println("LOG:espnow init failed");
        return;
    }
    esp_now_register_recv_cb(on_espnow_recv);

    esp_now_peer_info_t bcast = {};
    memset(bcast.peer_addr, 0xFF, 6);
    bcast.channel = CHANNEL;
    bcast.encrypt = false;
    esp_now_add_peer(&bcast);

    uint8_t mac[6];
    WiFi.macAddress(mac);
    Serial.printf("LOG:LC Bridge ready mac=%02X:%02X:%02X:%02X:%02X:%02X channel=%d\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], (int)CHANNEL);
    send_usb_frame(0x03, mac, nullptr, 0);
}

void loop() {
    poll_usb();

    static uint32_t last_status = 0;
    if (millis() - last_status > 30000) {
        last_status = millis();
        Serial.printf("LOG:bridge rx=%lu tx=%lu heap=%lu\n",
                      (unsigned long)rx_requests, (unsigned long)tx_responses,
                      (unsigned long)ESP.getFreeHeap());
    }

    delay(2);
}
