#include "../../arduino/presets/m5tab_preset.h"

using namespace lc;

RuntimeConfig kConfig = make_m5tab_preset();

DeviceRuntime kRuntime(kConfig);

void setup() {
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(25);
}
