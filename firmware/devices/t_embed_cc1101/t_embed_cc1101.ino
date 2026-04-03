#include "../../arduino/presets/t_embed_cc1101_preset.h"

using namespace lc;

RuntimeConfig kConfig = make_t_embed_cc1101_preset();

DeviceRuntime kRuntime(kConfig);

void setup() {
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(25);
}
