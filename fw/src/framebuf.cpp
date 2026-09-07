#include "framebuf.h"

FrameAssembler frames;

bool Coverage::add(uint32_t start, uint32_t end) {
    if (end <= start) return true;

    // Insert, keeping the list sorted and merged.  In the normal case the seven
    // packets arrive in order and this collapses to a single span.
    int i = 0;
    while (i < count_ && spans_[i].end < start) i++;

    if (i < count_ && spans_[i].start <= end) {
        // Overlaps or touches: widen this span and absorb any that follow.
        spans_[i].start = min(spans_[i].start, start);
        spans_[i].end = max(spans_[i].end, end);
        int j = i + 1;
        while (j < count_ && spans_[j].start <= spans_[i].end) {
            spans_[i].end = max(spans_[i].end, spans_[j].end);
            j++;
        }
        const int removed = j - i - 1;
        if (removed > 0) {
            for (int k = i + 1; k + removed < count_; k++)
                spans_[k] = spans_[k + removed];
            count_ -= removed;
        }
        return true;
    }

    if (count_ >= MAX_SPANS) return false;
    for (int k = count_; k > i; k--) spans_[k] = spans_[k - 1];
    spans_[i] = {start, end};
    count_++;
    return true;
}

void FrameAssembler::begin() {
    memset(buf_, 0, sizeof(buf_));
    cov_.reset();
    filling_ = 0;
    showing_ = 2;
    shared_.store(1, std::memory_order_relaxed);
    fresh_.store(false, std::memory_order_relaxed);
}

void FrameAssembler::write(uint32_t offset, const uint8_t *data, uint32_t len) {
    if (offset >= FRAME_BYTES) return;
    if (offset + len > FRAME_BYTES) len = FRAME_BYTES - offset;

    uint8_t *dst = buf_[filling_];

#if LED_ORDER_GRB
    // Reorder while copying.  The absolute byte index gives the channel, so
    // this is exact for any offset and length, not only aligned ones.
    for (uint32_t i = 0; i < len; i++) {
        const uint32_t abs = offset + i;
        const uint32_t px = abs / 3;
        const uint32_t ch = abs - px * 3;
        dst[px * 3 + CHANNEL_MAP[ch]] = data[i];
    }
#else
    memcpy(dst + offset, data, len);
#endif

    if (!cov_.add(offset, offset + len))
        overruns_.fetch_add(1, std::memory_order_relaxed);
}

bool FrameAssembler::latch() {
    if (cov_.empty()) {
        // A PUSH with nothing written since the last one.  Not an error: the
        // broadcast PUSH also reaches boards that had no data this frame.
        return false;
    }
    if (!cov_.covers(FRAME_BYTES)) {
        torn_.fetch_add(1, std::memory_order_relaxed);
        cov_.reset();
        return false;
    }
    cov_.reset();

    // Publish by exchanging our own slot with the shared one.  Whatever comes
    // back is a buffer nobody else holds.
    const int published = filling_;
    filling_ = shared_.exchange(published, std::memory_order_acq_rel);
    fresh_.store(true, std::memory_order_release);

    // Seed the new buffer with the frame just published, so a packet lost next
    // frame leaves those pixels one frame stale instead of two.  The published
    // buffer may be picked up by the main loop while this runs; both sides only
    // read it, so that is safe.
    memcpy(buf_[filling_], buf_[published], FRAME_BYTES);

    frames_.fetch_add(1, std::memory_order_relaxed);
    return true;
}

const uint8_t *FrameAssembler::acquire() {
    if (!fresh_.exchange(false, std::memory_order_acquire)) return nullptr;
    showing_ = shared_.exchange(showing_, std::memory_order_acq_rel);
    return buf_[showing_];
}
