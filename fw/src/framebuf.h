#pragma once
#include <Arduino.h>
#include <atomic>
#include "config.h"

// Frame assembly and buffering.
//
// The controller latches only complete frames.  A torn frame is dropped, not
// shown, so the wall never displays half of one picture and half of the next.
//
// "Complete" means the union of the byte ranges written since the last latch
// covers the whole 9216-byte buffer.  DDP is a write-at-offset protocol, so
// tracking a set of intervals is the only exact way to know that: counting
// bytes would call a duplicated packet a complete frame.
//
// Three buffers, not two.  Sending 12 x 256 LEDs takes 7.98 ms and the LED
// peripheral reads its buffer by DMA the whole time.  With two buffers a latch
// arriving mid-transmission would hand the network thread the buffer that is
// still being clocked out, and the wall would tear for real.  With three, the
// writer, the frame waiting to be shown and the frame being shown are always
// distinct, and no lock is needed on the receive path.

class Coverage {
  public:
    static constexpr int MAX_SPANS = 16;

    void reset() { count_ = 0; }
    bool empty() const { return count_ == 0; }

    // Merge [start, end) into the set.  Returns false if the set overflowed,
    // in which case the frame is treated as incomplete - conservative, and it
    // cannot happen with the seven packets per frame the Pi actually sends.
    bool add(uint32_t start, uint32_t end);

    bool covers(uint32_t total) const {
        return count_ == 1 && spans_[0].start == 0 && spans_[0].end >= total;
    }

    uint32_t bytes() const {
        uint32_t n = 0;
        for (int i = 0; i < count_; i++) n += spans_[i].end - spans_[i].start;
        return n;
    }

  private:
    struct Span { uint32_t start, end; };
    Span spans_[MAX_SPANS];
    int count_ = 0;
};

class FrameAssembler {
  public:
    void begin();

    // ---- receive side: called only from the UDP callback task -------------

    // Writes into the buffer being filled, applying the RGB -> GRB channel map,
    // and records the coverage.
    void write(uint32_t offset, const uint8_t *data, uint32_t len);

    // A zero-length PUSH.  Publishes the filled buffer if it is complete;
    // otherwise counts a torn frame and drops it.  True if a frame was
    // published.
    bool latch();

    void discard() { cov_.reset(); }

    // ---- display side: called only from the main loop ---------------------

    // Claim the newest published frame, if there is one newer than the frame
    // currently held.  The returned pointer stays valid until the next call.
    const uint8_t *acquire();

    // The frame currently held for display, whether or not it is new.
    uint8_t *held() { return buf_[showing_]; }

    // ---- stats -----------------------------------------------------------
    uint32_t frames() const { return frames_; }
    uint32_t torn() const { return torn_; }
    uint32_t overruns() const { return overruns_; }
    uint32_t coveredBytes() const { return cov_.bytes(); }

  private:
    // The classic lock-free triple buffer.  Each side only ever exchanges its
    // OWN slot index with the shared one, so the three indices stay a
    // permutation of {0,1,2} at all times and neither side can ever end up
    // pointing at the buffer the other is using.
    uint8_t buf_[3][FRAME_BYTES];
    int filling_ = 0;                    // touched only by the UDP task
    int showing_ = 2;                    // touched only by the main loop
    std::atomic<int> shared_{1};
    std::atomic<bool> fresh_{false};

    Coverage cov_;
    std::atomic<uint32_t> frames_{0};
    std::atomic<uint32_t> torn_{0};
    std::atomic<uint32_t> overruns_{0};
};

extern FrameAssembler frames;
