#include "../../arduino/presets/m5stickc_plus2_preset.h"

using namespace lc;

RuntimeConfig kConfig = make_m5stickc_plus2_preset();

DeviceRuntime kRuntime(kConfig);

void setup() {
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(25);
}
