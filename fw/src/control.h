#pragma once
#include <Arduino.h>

// The control plane, UDP 4049.  Port 4048 carries pixels and nothing else, so
// a control message can never be mistaken for a frame.
//
// This board broadcasts an announcement every two seconds carrying its factory
// MAC, its column if it has one, and its running firmware version.  That is how
// the Pi discovers an unassigned board, how commissioning works, and how the
// driver can report what every controller is running.

namespace control {

bool begin();
void tick();

// Set by the receive callback, acted on by the main loop: an OTA must not run
// inside a network callback.
bool otaRequested(String &url, String &sha);

}  // namespace control
