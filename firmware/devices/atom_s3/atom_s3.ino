#include "../../arduino/presets/atom_s3_preset.h"

using namespace lc;

RuntimeConfig kConfig = make_atom_s3_preset();

DeviceRuntime kRuntime(kConfig);

void setup() {
    kRuntime.begin();
}

void loop() {
    kRuntime.loop();
    delay(25);
}
