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
// static, held in NVS and set at commissioning.
//
// A board with no assignment asks for DHCP and, if nothing answers within
// DHCP_WAIT_MS, gives itself a MAC-derived address on the pixel segment -
// enough to be seen and commissioned, not enough to be mistaken for a working
// column. This used to say DHCP "means link-local" on this network. It does
// not: the ESP32 Ethernet driver has no IPv4 link-local autoconfiguration, so
// a board with no DHCP server simply stayed at 0.0.0.0 and never announced.
// The pixel segment has no DHCP server by design, so that was every board in
// the field; it went unnoticed because the bench LAN has one. See the
// addressing block in config.h.

namespace net {

bool begin();
bool linkUp();
IPAddress localIP();
const char *macString();
uint32_t linkDrops();
void tick();

}  // namespace net
