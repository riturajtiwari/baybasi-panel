#pragma once
#include <Arduino.h>

// The on-board RGB LED on GPIO 48.  It is driven with the Arduino core's
// neopixelWrite(), which uses one RMT channel - the LED outputs use LCD_CAM,
// so there is no contention.
//
// This is the only thing you can see when the board is behind a panel, in an
// enclosure, mid-column.  It is worth getting right.

namespace status {

enum class State {
    Booting,       // red          - powered, nothing else true yet
    NoLink,        // red, blink   - Ethernet is down
    NoSignal,      // amber        - link up, no DDP for over 500 ms
    Buffering,     // blue         - receiving, outputs still disabled
    Running,       // green, dim   - showing frames
    Torn,          // magenta      - frames arriving incomplete
    Updating,      // white pulse  - OTA in progress
    Identify,      // white flash  - "which board am I", from the Pi
    Fault,         // red, fast    - something is wrong; check the log
};

void begin();
void set(State s);
State get();
void identify(uint32_t ms);
// True while an identify is running. main.cpp uses this to take over the
// panels, which is the part an operator can see.
bool identifying();
void tick();   // call from loop()

}  // namespace status
