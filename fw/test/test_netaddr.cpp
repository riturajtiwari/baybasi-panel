// Host test for the pre-commissioning fallback address.
//
// This is the address an unassigned board gives itself when nothing answers
// DHCP, which on the pixel segment is always. It is the only way such a board
// can be found, so the arithmetic has to be right for every MAC, not for the
// one on the bench. An off-by-one lands a board on .0 or .255: unreachable,
// and a nuisance to every other host on the segment.
//
//   c++ -std=c++17 -I fw/test/shim fw/test/test_netaddr.cpp -o /tmp/t && /tmp/t

#include "../src/config.h"

#include <cstdio>
#include <set>

static int failures = 0;
#define CHECK(cond, msg)                                                    \
    do {                                                                    \
        if (!(cond)) { printf("  FAIL %s\n", msg); failures++; }            \
        else printf("  ok   %s\n", msg);                                    \
    } while (0)

int main() {
    printf("fallback address\n");

    // Exhaustive: there are only 65536 possible inputs, so sample nothing.
    int lo = 999, hi = -1;
    bool hitsNetwork = false, hitsBroadcast = false;
    bool hitsPi = false, hitsColumn = false;
    for (int a = 0; a < 256; a++) {
        for (int b = 0; b < 256; b++) {
            const int h = fallbackHostByte((uint8_t)a, (uint8_t)b);
            if (h < lo) lo = h;
            if (h > hi) hi = h;
            if (h == 0) hitsNetwork = true;
            if (h == 255) hitsBroadcast = true;
            if (h == 1) hitsPi = true;
            if (h >= 11 && h <= 14) hitsColumn = true;
        }
    }
    CHECK(!hitsNetwork, "never lands on .0, the network address");
    CHECK(!hitsBroadcast, "never lands on .255, the broadcast address");
    CHECK(!hitsPi, "never lands on .1, which is the Pi");
    CHECK(!hitsColumn, "never lands on .11-.14, the commissioned columns");
    CHECK(lo == FALLBACK_HOST_MIN, "lowest host is the configured minimum");
    CHECK(hi == FALLBACK_HOST_MIN + FALLBACK_HOST_SPAN - 1,
          "highest host is min + span - 1");

    // Deterministic: an address written on a sticker has to stay true.
    CHECK(fallbackHostByte(0x83, 0x8d) == fallbackHostByte(0x83, 0x8d),
          "same MAC gives the same address twice");

    // The bench board, so a wrong constant shows up as a changed expectation
    // rather than as a board that quietly moved.
    CHECK(fallbackHostByte(0x83, 0x8d) == 125,
          "ae:27:6e:a5:83:8d -> 192.168.50.125");

    // Consecutive MACs from one production run must not pile up.
    std::set<int> spread;
    for (int b = 0; b < 8; b++) spread.insert(fallbackHostByte(0x83, (uint8_t)(0x8d + b)));
    CHECK(spread.size() == 8, "eight consecutive MACs give eight addresses");

    // The whole range is reachable, so the span is not silently narrowed.
    std::set<int> all;
    for (int a = 0; a < 256; a++)
        for (int b = 0; b < 256; b++) all.insert(fallbackHostByte((uint8_t)a, (uint8_t)b));
    CHECK((int)all.size() == FALLBACK_HOST_SPAN, "every slot in the span is reachable");

    printf(failures ? "\nFAILED (%d)\n" : "\nall passed\n", failures);
    return failures ? 1 : 0;
}
