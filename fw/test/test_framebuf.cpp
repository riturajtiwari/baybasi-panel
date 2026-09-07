// Host tests for the frame assembler.
//
// Two things are worth proving without hardware: that "complete frame" means
// what it should (the interval set), and that the triple buffer never hands the
// same buffer to the network thread and the display thread at once. The second
// is a data race, so it is tested with real threads under -fsanitize=thread.

#include "../src/framebuf.h"

#include <atomic>
#include <cassert>
#include <cstdio>
#include <thread>
#include <vector>

static int failures = 0;
#define CHECK(cond, msg)                                                    \
    do {                                                                    \
        if (!(cond)) { printf("  FAIL %s\n", msg); failures++; }            \
        else printf("  ok   %s\n", msg);                                    \
    } while (0)

static void test_coverage() {
    printf("coverage\n");
    {
        Coverage c;
        // The seven packets the Pi actually sends: six of 1440, one of 576.
        for (uint32_t off = 0; off < FRAME_BYTES; off += 1440)
            c.add(off, min<uint32_t>(off + 1440, FRAME_BYTES));
        CHECK(c.covers(FRAME_BYTES), "seven in-order packets complete a frame");
        CHECK(c.bytes() == FRAME_BYTES, "byte count is exact");
    }
    {
        Coverage c;
        // Same bytes, reverse order: reassembly must not depend on arrival order.
        std::vector<uint32_t> offs;
        for (uint32_t off = 0; off < FRAME_BYTES; off += 1440) offs.push_back(off);
        for (auto it = offs.rbegin(); it != offs.rend(); ++it)
            c.add(*it, min<uint32_t>(*it + 1440, FRAME_BYTES));
        CHECK(c.covers(FRAME_BYTES), "out-of-order packets still complete");
    }
    {
        Coverage c;
        // One packet lost. This is the case that must NOT be shown.
        for (uint32_t off = 0; off < FRAME_BYTES; off += 1440) {
            if (off == 2880) continue;
            c.add(off, min<uint32_t>(off + 1440, FRAME_BYTES));
        }
        CHECK(!c.covers(FRAME_BYTES), "a lost packet leaves the frame incomplete");
    }
    {
        Coverage c;
        // A duplicated packet must not be mistaken for progress: this is the
        // bug you get from counting bytes instead of tracking intervals.
        for (int i = 0; i < 8; i++) c.add(0, 1440);
        CHECK(!c.covers(FRAME_BYTES), "duplicates do not complete a frame");
        CHECK(c.bytes() == 1440, "duplicates are counted once");
    }
    {
        Coverage c;
        c.add(0, 100); c.add(200, 300); c.add(100, 200);
        CHECK(c.covers(300), "a gap filled in later merges into one span");
    }
    {
        Coverage c;
        // Overlapping writes, which a retransmit could produce.
        c.add(0, 5000); c.add(4000, FRAME_BYTES);
        CHECK(c.covers(FRAME_BYTES), "overlapping writes complete");
    }
    {
        Coverage c;
        bool ok = true;
        // More disjoint spans than the set can hold: must fail closed.
        for (int i = 0; i < Coverage::MAX_SPANS + 4; i++)
            ok &= c.add(i * 100, i * 100 + 10);
        CHECK(!ok, "overflowing the span set is reported, not ignored");
        CHECK(!c.covers(FRAME_BYTES), "an overflowed frame is never complete");
    }
}

static void fillFrame(FrameAssembler &f, uint8_t value, bool dropOne = false) {
    static uint8_t pkt[1440];
    memset(pkt, value, sizeof(pkt));
    for (uint32_t off = 0; off < FRAME_BYTES; off += 1440) {
        if (dropOne && off == 1440) continue;
        const uint32_t n = min<uint32_t>(1440, FRAME_BYTES - off);
        f.write(off, pkt, n);
    }
}

static void test_latch() {
    printf("latch\n");
    static FrameAssembler f;
    f.begin();

    CHECK(!f.latch(), "a PUSH with nothing written is not a frame");

    fillFrame(f, 0x11);
    CHECK(f.latch(), "a complete frame latches");
    const uint8_t *a = f.acquire();
    CHECK(a != nullptr, "the display side sees it");
#if LED_ORDER_GRB
    CHECK(a && a[0] == 0x11, "channel reorder preserves a uniform frame");
#endif

    fillFrame(f, 0x22, /*dropOne=*/true);
    const uint32_t tornBefore = f.torn();
    CHECK(!f.latch(), "a torn frame does not latch");
    CHECK(f.torn() == tornBefore + 1, "the torn frame is counted");
    CHECK(f.acquire() == nullptr, "and never reaches the display");

    CHECK(f.acquire() == nullptr, "acquire twice yields nothing the second time");
}

static void test_channel_order() {
#if LED_ORDER_GRB
    printf("channel order\n");
    static FrameAssembler f;
    f.begin();
    // One red pixel, sent as RGB, must land as GRB in the LED buffer.
    static uint8_t buf[FRAME_BYTES];
    memset(buf, 0, sizeof(buf));
    buf[0] = 0xAA;  // R
    buf[1] = 0xBB;  // G
    buf[2] = 0xCC;  // B
    // Split across packet boundaries at a non-multiple-of-3 offset, which is
    // the case a naive implementation gets wrong.
    f.write(0, buf, 1);
    f.write(1, buf + 1, 1);
    f.write(2, buf + 2, FRAME_BYTES - 2);
    CHECK(f.latch(), "byte-at-a-time writes still complete");
    const uint8_t *p = f.acquire();
    CHECK(p && p[0] == 0xBB && p[1] == 0xAA && p[2] == 0xCC,
          "RGB in, GRB out, even across packet boundaries");
#endif
}

// The one that matters: the writer and the display must never hold the same
// buffer. Run it under -fsanitize=thread as well as checking the invariant.
static void test_triple_buffer_race() {
    printf("triple buffer under contention\n");
    static FrameAssembler f;
    f.begin();

    std::atomic<bool> stop{false};
    std::atomic<int> published{0}, acquired{0}, aliased{0};

    std::thread producer([&] {
        uint8_t v = 0;
        while (!stop.load()) {
            fillFrame(f, ++v);
            if (f.latch()) published.fetch_add(1);
        }
    });

    std::thread consumer([&] {
        while (!stop.load()) {
            const uint8_t *frame = f.acquire();
            if (!frame) continue;
            acquired.fetch_add(1);
            // Hold it the way the LED DMA does, then check it did not change
            // underneath us: a uniform frame that is no longer uniform means
            // the writer was handed the buffer we are showing.
            const uint8_t first = frame[0];
            for (int i = 0; i < 400; i++) {
                if (frame[(i * 977) % FRAME_BYTES] != first) {
                    aliased.fetch_add(1);
                    break;
                }
            }
        }
    });

    std::this_thread::sleep_for(std::chrono::seconds(2));
    stop.store(true);
    producer.join();
    consumer.join();

    printf("  published=%d acquired=%d\n", published.load(), acquired.load());
    CHECK(published.load() > 100, "the producer made progress");
    CHECK(acquired.load() > 10, "the consumer saw frames");
    CHECK(aliased.load() == 0, "the shown buffer is never written underneath");
}

int main() {
    test_coverage();
    test_latch();
    test_channel_order();
    test_triple_buffer_race();
    printf(failures ? "\n%d FAILURE(S)\n" : "\nall firmware logic tests passed\n",
           failures);
    return failures ? 1 : 0;
}
