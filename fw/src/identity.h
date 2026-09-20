#pragma once
#include <Arduino.h>
#include "config.h"

// Board identity: which column this board drives, and the address it takes.
//
// It lives in NVS rather than in the image, so all four boards run one binary
// and an OTA never touches the assignment.  A board with no assignment comes up
// on DHCP - falling back to a MAC-derived address on the pixel segment, which
// has no DHCP server - announces its factory MAC, and waits for the Pi to tell
// it which column it is.  See net.h.
//
// The W5500's MAC is the chip's factory Ethernet MAC, so the identity the Pi
// sees on the wire and the identity in the announcement cannot drift apart.

struct Identity {
    int8_t   column = COLUMN_UNASSIGNED;
    uint32_t ip = 0;             // 0 = use DHCP
    uint32_t gateway = 0;
    uint32_t netmask = 0;
    uint8_t  ddpId = 1;
    uint16_t pixels = NUM_LEDS;

    bool assigned() const { return column >= 0; }
};

namespace identity {

void begin();
const Identity &get();

// Persist a new assignment.  Returns false if NVS refused the write, which is
// worth knowing: an assignment that did not stick comes back as unassigned
// after the next reboot and looks like a dead board.
bool assign(int8_t column, uint32_t ip, uint32_t gw, uint32_t mask,
            uint8_t ddpId, uint16_t pixels);
bool clear();

// Factory MAC, lower case, colon separated.  This is the name the Pi knows the
// board by, and it is unique per chip.
const char *macString();
void macBytes(uint8_t out[6]);

}  // namespace identity
