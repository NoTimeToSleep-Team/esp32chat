#include "../../arduino/presets/m5cardputer_adv_preset.h"

using namespace lc;

RuntimeConfig kConfig = make_m5cardputer_adv_preset();

DeviceRuntime kRuntime(kConfig);

void setup() {
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(25);
}
