#pragma once
#include <Arduino.h>

// Over-the-air update, fetched from the Pi over Ethernet.
//
// The boards end up mid-column, inside enclosures, behind panels, and the
// enclosure has no USB opening.  The first flash is over USB on the bench;
// everything after that is this.
//
// The image is verified against a SHA-256 supplied by the Pi BEFORE the new
// slot is marked bootable, so a truncated download reboots into the old image
// instead of into nothing.  Recovery from a bad flash is still to pull the
// devkit out of its sockets, which is why they are sockets.

namespace ota {

bool inProgress();
const char *lastError();

// Blocking.  Call from the main loop, not from a network callback.
bool update(const String &url, const String &expectedSha256);

}  // namespace ota
