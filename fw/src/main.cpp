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

    status::tick();
    control::tick();
    net::tick();

    // An OTA is requested from a network callback and executed here, because it
    // blocks for seconds and reboots the board when it succeeds.
    String url, sha;
    if (control::otaRequested(url, sha)) ota::update(url, sha);

    // ---- a new complete frame -------------------------------------------
    if (const uint8_t *frame = frames.acquire()) {
        leds::show(frame);
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
