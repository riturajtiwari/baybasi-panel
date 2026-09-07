#pragma once
#include <Arduino.h>

// Ethernet: a WIZnet W5500 on SPI, brought up with the arduino-esp32 3.x
// ETH driver.
//
// The MAC comes from the chip's factory Ethernet MAC, so the address the Pi
// sees on the wire and the address in the announcement are the same value and
// cannot drift apart.
//
// Addressing follows the handoff: the Pi is .1 and controllers are .11 to .14,
// static, held in NVS and set at commissioning.  A board with no assignment
// takes DHCP, which on this network means link-local - enough to be seen and
// commissioned, not enough to be mistaken for a working column.

namespace net {

bool begin();
bool linkUp();
IPAddress localIP();
const char *macString();
uint32_t linkDrops();
void tick();

}  // namespace net
