// Baybasi pixel wall — standalone ROW test
//
// Flash it, unplug the laptop, leave it running. Four patterns cycle forever on
// a row of four daisy-chained 16x16 WS2812B panels (1024 LEDs on one wire).
// Nothing waits on serial and nothing ever finishes, so the dev kit drives the
// panels on its own. Runs on a CLASSIC ESP32 devkit (ESP-WROOM-32, 30-pin,
// HW-394 or similar).
//
// This is NOT the production topology. The real controller gives each panel its
// own output: 256 LEDs per wire, 8 ms a frame, twelve in parallel. Chaining is a
// bench convenience. Nothing here transfers to ../fw except the serpentine map.
//
// POWER IS THE WHOLE DESIGN CONSTRAINT. 1024 LEDs at white is ~61 A and no
// bench supply wants that, least of all unattended. So no pattern here ever
// lights more than 256 LEDs at once, and most light far fewer. That is not only
// safer, it looks better: FastLED scales the whole frame down to fit the current
// cap, so lighting less at a time means what IS lit runs near full brightness.
//
// The onboard LED blinks once a second. If the panels are dark but that LED is
// blinking, the firmware is alive and the fault is power, data or the panels —
// not a crashed board. That is the only diagnostic you get with no laptop, and
// it is worth more than it looks.

#include <Arduino.h>
#include <FastLED.h>

// ---------------------------------------------------------------- hardware --
// One output; the panels are chained back to back. GPIO 13 avoids every ESP32
// strapping pin (0, 2, 5, 12, 15) and every input-only pin (34, 35, 36, 39).
//
// GPIO 12 is the one that bites: held high at reset it sets the flash voltage
// wrong and the board will not boot. On the header it sits between D14 and D13,
// so count pins rather than trusting the gap.
// NOT "LED_PIN". FastLED uses that name as a template parameter in 42 of its
// headers, so -DDATA_PIN=4 on the command line rewrites `int DATA_PIN,` to
// `int 4,` and the library will not compile. Defining it in this file after
// #include <FastLED.h> is safe, which is why the classic env never noticed;
// a build flag is not. Found 2026-09-15 building the S3 env for the first time.
#ifndef LED_PIN
#define LED_PIN    13     // classic ESP32; the S3 envs override this to 4
#endif
#ifndef STATUS_LED
#define STATUS_LED 2      // the onboard LED next to PWR on this board
#endif

#define PANEL_W 16
#define PANEL_H 16
#define PANEL_LEDS (PANEL_W * PANEL_H)

// A row of the wall is four panels. Override with -DPANELS=n for a single panel
// (1) or a whole column (12); every pattern scales itself to fit.
#ifndef PANELS
#define PANELS 4
#endif
#define N_LEDS (PANELS * PANEL_LEDS)

// These panels are older than the WS2812B the wall is specified around. Wrong
// chipset looks exactly like a dead row, so rule it out before condemning
// hardware: add one of
//   -DLED_CHIPSET=WS2811   -DLED_CHIPSET=WS2812   -DLED_CHIPSET=SK6812
// to build_flags in platformio.ini.
#ifndef LED_CHIPSET
#define LED_CHIPSET WS2812B
#endif

// Current budget. FastLED rescales brightness every frame to stay inside it, so
// a mistake dims the row rather than browning out the supply or melting a lead.
// SET THIS TO WHAT YOUR BENCH SUPPLY CAN ACTUALLY DELIVER.
#ifndef SUPPLY_VOLTS
#define SUPPLY_VOLTS 5
#endif
#ifndef SUPPLY_MA
#define SUPPLY_MA    5000
#endif

#define BAND_ROWS 2       // band pattern: 2 rows x 16 x PANELS = 128 LEDs lit
#define BLOCK     64      // block pattern: a quarter panel, lit at any instant

// The trace is paced to a fixed wall-clock duration rather than one LED per
// frame, because frame time scales with chain length and the useful speed does
// not. One panel runs at ~130 fps, so a per-frame trace would cross it in two
// seconds and you would never see where it stopped. Floored by the frame time:
// a long chain is frame-limited and simply takes longer.
#define TRACE_MS  20000

CRGB leds[N_LEDS];

// ----------------------------------------------------------------- mapping --
// Column-serpentine inside one panel, the same formula the driver uses:
//   local = x * 16 + (y if x even else 15 - y)
// The band pattern uses it, so a scrambled band means this is wrong for your
// panels. The other patterns work in raw chain order on purpose: when you are
// checking wiring you want the physical chain, not an interpretation of it.
static inline uint16_t px(uint8_t panel, uint8_t x, uint8_t y) {
    return panel * PANEL_LEDS + (uint16_t)x * PANEL_H + ((x & 1) ? (PANEL_H - 1 - y) : y);
}

// ---------------------------------------------------------------- patterns --
// Ordered so the lit-LED count falls as you go down, and so the first thing you
// see after a reset is the one that proves the chain.
enum Pattern {
    P_WALK,    // one panel white at a time   256 lit   chain order and aliveness
    P_BAND,    // a sliding band on each panel 128 lit  all panels at once, hues cycling
    P_BLOCK,   // a block marching the row      64 lit  every LED in six colours
    P_TRACE,   // one LED end to end             1 lit  exactly where the chain stops
    P_COUNT
};

struct Step { const char *name; uint32_t ms; uint16_t lit; };

// ms == 0 means the pattern steps once per frame and says when it is done, so a
// slow frame can never make it skip an LED.
static const Step STEPS[P_COUNT] = {
    {"panel walk", PANELS * 700UL, PANEL_LEDS},
    {"band",       12000,          BAND_ROWS * PANEL_W * PANELS},
    {"block",      0,              BLOCK},
    {"trace",      0,              1},
};

static uint8_t  pattern   = P_WALK;
static uint32_t stepStart = 0;
static uint32_t pos       = 0;      // frame-stepped cursor for block and trace
static bool     done      = false;
static int      lastNote  = -1;
static uint32_t lastAdv   = 0;   // paces the trace

static void clear() { fill_solid(leds, N_LEDS, CRGB::Black); }

static void renderWalk(uint32_t t) {
    clear();
    int p = (t / 700) % PANELS;
    fill_solid(&leds[p * PANEL_LEDS], PANEL_LEDS, CRGB::White);
    if (p != lastNote) { lastNote = p; Serial.printf("    panel %d\n", p); }
}

// Every panel shows a band at the same height, so one glance tells you all four
// are alive. The band slides and the hue rotates, which also proves the colour
// channels without ever lighting a whole panel.
static void renderBand(uint32_t t) {
    clear();
    uint8_t row = (t / 250) % PANEL_H;
    uint8_t hue = (uint8_t)((t / 250) * 11);
    for (int p = 0; p < PANELS; p++)
        for (uint8_t r = 0; r < BAND_ROWS; r++)
            for (uint8_t x = 0; x < PANEL_W; x++)
                leds[px(p, x, (row + r) % PANEL_H)] = CHSV(hue, 255, 255);
}

// A quarter-panel block marches the whole row, once per colour. The lit count is
// fixed no matter how long the chain is, so this runs at genuine full brightness
// and still exercises every LED in every channel.
static void renderBlock() {
    static const CRGB  C[6]  = {CRGB::White, CRGB::Red,    CRGB::Green,
                                CRGB::Blue,  CRGB::Yellow, CRGB::Cyan};
    static const char *NM[6] = {"white", "red", "green", "blue", "yellow", "cyan"};
    const uint32_t STRIDE = 8;                  // LEDs advanced per frame
    const uint32_t SPAN   = N_LEDS / STRIDE;    // frames in one colour pass

    uint32_t phase = pos / SPAN;
    if (phase >= 6) { done = true; return; }
    uint32_t start = (pos % SPAN) * STRIDE;

    clear();
    for (uint32_t i = 0; i < BLOCK; i++)
        if (start + i < N_LEDS) leds[start + i] = C[phase];

    if ((int)phase != lastNote) {
        lastNote = (int)phase;
        Serial.printf("    %s\n", NM[phase]);
    }
    pos++;
}

// One LED at a time, nothing skipped, paced to about 20 seconds whatever the
// chain length. The index is printed in case a laptop is attached, but the point
// is that you can watch where the dot stops without one.
static void renderTrace() {
    uint32_t now = millis();
    if (now - lastAdv < (uint32_t)(TRACE_MS / N_LEDS)) return;    // hold this frame
    lastAdv = now;

    for (uint16_t i = 0; i < N_LEDS; i++) leds[i].nscale8(140);   // short tail
    if (pos < N_LEDS) leds[pos] = CRGB::White;
    if (pos % 64 == 0 && pos < N_LEDS)
        Serial.printf("    LED %4lu   (panel %lu, pixel %lu)\n",
                      (unsigned long)pos,
                      (unsigned long)(pos / PANEL_LEDS),
                      (unsigned long)(pos % PANEL_LEDS));
    if (++pos >= N_LEDS + 16) done = true;      // +16 lets the tail fade out
}

// -------------------------------------------------------------------- main --
static void enter(uint8_t p) {
    pattern   = p;
    stepStart = millis();
    pos       = 0;
    done      = false;
    lastNote  = -1;
    lastAdv   = 0;
    clear();
    Serial.printf("\n[%d/%d] %s   (max %u LEDs lit, ~%.1f A before capping)\n",
                  p + 1, P_COUNT, STEPS[p].name, STEPS[p].lit, STEPS[p].lit * 0.060f);
}

static void banner() {
    float frame = N_LEDS * 0.030f;
    Serial.println(F("\n=== Baybasi standalone row test =============================="));
    Serial.printf("  %d panels chained on GPIO %d  =  %d LEDs\n", PANELS, LED_PIN, N_LEDS);
    Serial.printf("  frame ~%.0f ms (~%.0f fps).  Whole string white would be ~%.0f A.\n",
                  frame, 1000.0f / frame, N_LEDS * 0.060f);
    Serial.printf("  Cap %.1f A.  No pattern lights more than %d LEDs (~%.1f A).\n",
                  SUPPLY_MA / 1000.0f, PANEL_LEDS, PANEL_LEDS * 0.060f);
    Serial.println(F("  Runs forever with no laptop attached. Onboard LED blinks 1 Hz"));
    Serial.println(F("  while the firmware is alive: panels dark + LED blinking means"));
    Serial.println(F("  power, data or panels, not a crashed board."));
    Serial.println(F("  Far panels dim or orange = voltage drop. Inject 5 V at both"));
    Serial.println(F("  ends of the chain before believing an LED is dead."));
    Serial.println(F("=============================================================="));
}

void setup() {
    Serial.begin(115200);              // harmless with nothing attached
    pinMode(STATUS_LED, OUTPUT);

#ifdef OE_PIN
    // Talking to a panel THROUGH the production controller board. Its twelve
    // outputs pass two SN74AHCT245s whose /OE is pulled HIGH by R15, so they
    // come out of reset DISABLED and stay that way until this pin goes low.
    //
    // Park the data line low FIRST. The 245 is a buffer, not a latch: enable it
    // while its input is still a floating ESP32 pad and it drives that float
    // straight at a panel's DIN. Order matters, one line of code apart.
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    pinMode(OE_PIN, OUTPUT);
    digitalWrite(OE_PIN, LOW);
    Serial.printf("  /OE on GPIO %d driven LOW: 245 outputs enabled\n", OE_PIN);
#endif

    FastLED.addLeds<LED_CHIPSET, LED_PIN, GRB>(leds, N_LEDS);
    FastLED.setMaxPowerInVoltsAndMilliamps(SUPPLY_VOLTS, SUPPLY_MA);
    FastLED.setBrightness(255);        // the power cap does the real limiting
    FastLED.clear(true);

    banner();
    enter(P_WALK);
}

void loop() {
    uint32_t now = millis();
    digitalWrite(STATUS_LED, (now / 500) % 2);   // 1 Hz "firmware is alive"

    uint32_t t = now - stepStart;
    bool over = STEPS[pattern].ms ? (t >= STEPS[pattern].ms) : done;
    if (over) {
        enter((pattern + 1) % P_COUNT);          // wraps forever
        t = 0;
    }

    switch (pattern) {
        case P_WALK:  renderWalk(t);  break;
        case P_BAND:  renderBand(t);  break;
        case P_BLOCK: renderBlock();  break;
        case P_TRACE: renderTrace();  break;
        default:      clear();        break;
    }
    FastLED.show();
}
