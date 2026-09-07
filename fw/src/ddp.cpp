#include "ddp.h"
#include <AsyncUDP.h>
#include "config.h"
#include "framebuf.h"
#include "identity.h"

namespace {

AsyncUDP g_udp;
ddp::Stats g_stats;

constexpr uint8_t HEADER_LEN = 10;
constexpr uint8_t FLAG_VERSION_MASK = 0xC0;
constexpr uint8_t FLAG_VERSION_1 = 0x40;
constexpr uint8_t FLAG_TIMECODE = 0x10;
constexpr uint8_t FLAG_PUSH = 0x01;
constexpr uint8_t ID_DEFAULT_OUTPUT = 1;
constexpr uint8_t ID_ALL = 255;

inline bool addressedToUs(uint8_t destId) {
    const uint8_t mine = identity::get().ddpId;
    return destId == mine || destId == ID_DEFAULT_OUTPUT || destId == ID_ALL;
}

// Runs in the lwIP task.  Everything here is a bounded copy; anything that can
// block, and the LED transmission itself, belongs in the main loop.
void onPacket(AsyncUDPPacket &pkt) {
    const uint8_t *p = pkt.data();
    const size_t len = pkt.length();

    g_stats.packets++;
    g_stats.bytes += len;

    if (len < HEADER_LEN) { g_stats.malformed++; return; }
    if ((p[0] & FLAG_VERSION_MASK) != FLAG_VERSION_1) { g_stats.malformed++; return; }
    if (p[0] & FLAG_TIMECODE) { g_stats.malformed++; return; }  // we never send one

    const uint8_t sequence = p[1] & 0x0F;
    const uint8_t destId = p[3];
    const uint32_t offset = ((uint32_t)p[4] << 24) | ((uint32_t)p[5] << 16) |
                            ((uint32_t)p[6] << 8) | (uint32_t)p[7];
    const uint16_t dataLen = ((uint16_t)p[8] << 8) | (uint16_t)p[9];

    if (p[0] & FLAG_PUSH) {
        g_stats.pushes++;
        g_stats.lastPacketMs = millis();
        // The broadcast PUSH is zero length.  A PUSH riding on a data packet is
        // the Pi latching one controller early; honour the data, then latch.
        if (dataLen && len >= (size_t)HEADER_LEN + dataLen && addressedToUs(destId))
            frames.write(offset, p + HEADER_LEN, dataLen);
        frames.latch();
        return;
    }

    if (!dataLen) return;
    if (!addressedToUs(destId)) { g_stats.rejected++; return; }
    if (len < (size_t)HEADER_LEN + dataLen) { g_stats.malformed++; return; }
    if (offset >= FRAME_BYTES) { g_stats.oversize++; return; }

    if (sequence) {
        const uint8_t expected = g_stats.lastSequence % 15 + 1;
        if (g_stats.lastSequence && sequence != expected &&
            sequence != g_stats.lastSequence)
            g_stats.sequenceGaps++;
        g_stats.lastSequence = sequence;
    }

    frames.write(offset, p + HEADER_LEN, dataLen);
    g_stats.lastPacketMs = millis();
}

}  // namespace

namespace ddp {

bool begin() {
    if (!g_udp.listen(DDP_PORT)) {
        log_e("cannot listen on udp/%u", DDP_PORT);
        return false;
    }
    g_udp.onPacket(onPacket);
    log_i("DDP listening on udp/%u, %u bytes owned, ddp id %u",
          DDP_PORT, (unsigned)FRAME_BYTES, identity::get().ddpId);
    return true;
}

const Stats &stats() { return g_stats; }

uint32_t sinceLastPacket() {
    return g_stats.lastPacketMs ? (millis() - g_stats.lastPacketMs) : UINT32_MAX;
}

}  // namespace ddp
