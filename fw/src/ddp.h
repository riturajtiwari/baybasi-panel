#pragma once
#include <Arduino.h>

// DDP receive, UDP port 4048.
//
// This board knows how many bytes it owns and where they go on its twelve
// outputs.  It knows nothing about the wall's shape: the Pi holds all the
// geometry, so a mapping change is a YAML edit on the Pi and never a reflash
// of four boards behind eight feet of panels.
//
// Data packets are unicast to this board and never carry PUSH.  A single
// zero-length broadcast PUSH latches all four controllers on the same frame;
// latching per controller tears visibly at the column seams.

namespace ddp {

struct Stats {
    uint32_t packets = 0;
    uint32_t bytes = 0;
    uint32_t pushes = 0;
    uint32_t rejected = 0;      // not addressed to this board
    uint32_t malformed = 0;
    uint32_t oversize = 0;      // past the end of our 9216-byte buffer
    uint32_t lastPacketMs = 0;
    uint8_t  lastSequence = 0;
    uint32_t sequenceGaps = 0;
};

bool begin();
const Stats &stats();
uint32_t sinceLastPacket();

}  // namespace ddp
