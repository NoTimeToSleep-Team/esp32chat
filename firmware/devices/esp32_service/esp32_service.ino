#include "../../arduino/presets/esp32_service_preset.h"

using namespace lc;

RuntimeConfig kConfig = make_esp32_service_preset();

DeviceRuntime kRuntime(kConfig);

void setup() {
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(25);
}
