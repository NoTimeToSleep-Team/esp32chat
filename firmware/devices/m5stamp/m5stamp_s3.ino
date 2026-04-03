#include "../../arduino/presets/m5stamp_s3_preset.h"

using namespace lc;

RuntimeConfig kConfig = make_m5stamp_s3_preset();

DeviceRuntime kRuntime(kConfig);

void setup() {
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(25);
}
