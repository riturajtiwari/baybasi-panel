// Baybasi controller firmware.
//
// One image for all four boards.  A board learns which column it owns from NVS,
// set once at commissioning, so an OTA can never move column 3's identity onto
// column 1.  Everything else - the wall's shape, the panel chain, the row to
// output map, gamma, brightness - lives on the Pi.  This board knows only that
// it owns 9216 bytes and where they go on its twelve outputs.
//
// Order of events at power-up, which matters:
//
//   1. /OE stays HIGH.  The board's pull-up to 3V3E already holds it there
//      through boot, and the per-output pull-downs give every panel a defined
//      low.  Nothing on the wall lights up.
//   2. Ethernet comes up.  The W5500 gets a 50 ms wait after its reset is
//      released before any SPI traffic.
//   3. The first COMPLETE DDP frame is buffered and clocked out.
//   4. Only then does /OE go LOW and the wall becomes visible.
//
// Skipping step 3 is what makes a wall show noise at power-up.

#include <Arduino.h>
#include "config.h"
#include "control.h"
#include "ddp.h"
#include "framebuf.h"
#include "identity.h"
#include "leds.h"
#include "net.h"
#include "ota.h"
#include "status.h"

namespace {

bool g_haveFrame = false;
uint32_t g_lastShow = 0;
uint32_t g_lastLog = 0;
uint32_t g_fadeStarted = 0;
bool g_faded = false;
uint32_t g_shown = 0;
uint32_t g_tornAtLastCheck = 0;
// Throughput instrumentation. Added 2026-09-19 to chase a stall - frames
// assembled at 30 fps but only ~0.27/s reached the panel - and kept, because
// it is the one place that says whether the wall is actually keeping up.
//
// Baseline measured that day, twelve outputs, 256 LEDs each, FastLED S3/I2S:
// show() 5078 us avg against a 7680 us theoretical transfer, 15% duty at
// 30 fps, shown == frames, torn == 0. A show() average that climbs toward
// 33000 us, or shown falling behind frames, means the wall is dropping.
//
// All per-interval, reset at each log: a lifetime sum of microseconds would
// overflow uint32 after about eight hours of running and then report nonsense.
uint32_t g_showMaxUs = 0, g_showSumUs = 0, g_showN = 0;
uint32_t g_loops = 0, g_loopsAtLog = 0, g_lastLogMs = 0, g_acqNull = 0;

void logSummary() {
    const ddp::Stats &s = ddp::stats();
    log_i("col=%d ip=%s frames=%lu shown=%lu torn=%lu gaps=%lu pkts=%lu "
          "rejected=%lu malformed=%lu oversize=%lu heap=%lu",
          (int)identity::get().column, net::localIP().toString().c_str(),
          (unsigned long)frames.frames(), (unsigned long)g_shown,
          (unsigned long)frames.torn(), (unsigned long)s.sequenceGaps,
          (unsigned long)s.packets, (unsigned long)s.rejected,
          (unsigned long)s.malformed, (unsigned long)s.oversize,
          (unsigned long)ESP.getFreeHeap());
    {
        const uint32_t ms = millis() - g_lastLogMs;
        log_i("loop: %lu iterations in %lu ms = %lu Hz   (acquire() null %lu x)",
              (unsigned long)(g_loops - g_loopsAtLog), (unsigned long)ms,
              (unsigned long)(ms ? (g_loops - g_loopsAtLog) * 1000UL / ms : 0),
              (unsigned long)g_acqNull);
        g_loopsAtLog = g_loops; g_lastLogMs = millis(); g_acqNull = 0;
    }
    log_i("show(): n=%lu  avg=%lu us  max=%lu us   (baseline 5078 us)",
          (unsigned long)g_showN,
          (unsigned long)(g_showN ? g_showSumUs / g_showN : 0),
          (unsigned long)g_showMaxUs);
    g_showN = 0; g_showSumUs = 0; g_showMaxUs = 0;
}

void updateStatus() {
    if (ota::inProgress()) return;
    if (!net::linkUp()) { status::set(status::State::NoLink); return; }

    const uint32_t torn = frames.torn();
    const bool tearing = torn > g_tornAtLastCheck;
    g_tornAtLastCheck = torn;

    if (ddp::sinceLastPacket() > SIGNAL_TIMEOUT_MS)
        status::set(status::State::NoSignal);
    else if (!leds::outputsEnabled())
        status::set(status::State::Buffering);
    else if (tearing)
        status::set(status::State::Torn);
    else
        status::set(status::State::Running);
}

}  // namespace

void setup() {
    Serial.begin(115200);

    // First, before anything can drive the LED pins: hold the level shifters
    // disabled and blank the LED buffer.
    leds::begin();
    status::begin();
    frames.begin();

    delay(200);
    log_i("baybasi controller %s, %d outputs, %d px/output, %u bytes/frame",
          FW_VERSION, NUM_OUTPUTS, PANEL_LEDS, (unsigned)FRAME_BYTES);

    identity::begin();
    if (!identity::get().assigned())
        log_w("UNASSIGNED. This board is waiting for the Pi to give it a "
              "column. Its mac is %s.", identity::macString());

    if (!net::begin()) status::set(status::State::Fault);
    ddp::begin();
    control::begin();

    pinMode(PIN_SYNC, INPUT);   // J14, unpopulated; reserved for a hardware sync
}

void loop() {
    const uint32_t now = millis();
    g_loops++;

    status::tick();
    control::tick();
    net::tick();

    // An OTA is requested from a network callback and executed here, because it
    // blocks for seconds and reboots the board when it succeeds.
    String url, sha;
    if (control::otaRequested(url, sha)) ota::update(url, sha);

    // ---- a new complete frame -------------------------------------------
    const uint8_t *frame = frames.acquire();
    if (!frame) g_acqNull++;
    if (frame) {
        const uint32_t t_show = micros();
        leds::show(frame);
        const uint32_t dt = micros() - t_show;
        if (dt > g_showMaxUs) g_showMaxUs = dt;
        g_showSumUs += dt;
        g_showN++;
        g_shown++;
        g_lastShow = now;
        g_fadeStarted = 0;
        g_faded = false;

        if (!g_haveFrame) {
            g_haveFrame = true;
            // The first complete frame is now on its way out of the shift
            // registers.  Let it land, then open the level shifters and send it
            // again so the panels latch real pixels rather than whatever they
            // powered up holding.
            leds::waitDone();
            leds::enableOutputs();
            leds::show(frame);
            log_i("first complete frame shown; outputs enabled");
        }
    }

    // ---- signal loss ------------------------------------------------------
    // After 500 ms with no packets, fade to black.  A frozen wall looks like
    // working content and hides the fault.
    const uint32_t quiet = ddp::sinceLastPacket();
    if (g_haveFrame && quiet > SIGNAL_TIMEOUT_MS && !g_faded) {
        if (!g_fadeStarted) {
            g_fadeStarted = now;
            log_w("no pixels for %lu ms; fading out", (unsigned long)quiet);
        }
        if (now - g_lastShow >= IDLE_REFRESH_MS) {
            uint8_t *held = frames.held();
            if (now - g_fadeStarted >= FADE_MS) {
                leds::blackOut(held);
                g_faded = true;
            } else {
                leds::fadeStep(held, 4);
            }
            leds::show(held);
            g_lastShow = now;
        }
    }

    if (now - g_lastLog >= 10000) {
        g_lastLog = now;
        logSummary();
        updateStatus();
    } else {
        updateStatus();
    }

    delay(1);
}
