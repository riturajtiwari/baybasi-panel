// Baybasi pixel wall — rev B bring-up: one panel, and the column DIP switch
//
// The first test that needs a rev B board. The devkit is FULLY SEATED in
// A1L/A1R (rev B's 25.4 mm pitch), so unlike the ctrl-board env there are no
// flying leads and GPIO 9/16/17/18 are reachable for the first time.
//
// What it does: draws the column number the DIP switch is asking for, as a big
// digit on one 16x16 panel hung off J1, and prints the raw pin state to serial.
// Flip a slider and the digit changes within about 50 ms.
//
//   pio run -e ctrl-revb -t upload
//   pio device monitor
//
// TWO PHASES, AND WHY.
//
// Data into a panel whose 5 V is OFF back-feeds through its protection diodes
// and kills the driving GPIO (FABRICATION.md). Rather than rely on getting the
// power-up order right at the bench, this build makes it structural:
//
//   Phase 1, on boot: /OE stays HIGH. Both 245s are high-impedance and every
//     panel sees a defined low through R16-R27. The switch readout runs and
//     prints. YOU CAN TEST THE WHOLE DIP CIRCUIT HERE, with the panel dark and
//     unpowered - it is pure GPIO and owes the panel nothing.
//
//   Phase 2, when you say so: power the panel, press ENTER in the monitor, and
//     /OE goes LOW. Only then does anything reach J1.
//
// So a panel can sit connected and unpowered through a flash, a reset and as
// much switch-flipping as you like, and nothing is at risk. Build with
// -DAUTO_ENABLE=1 to skip the gate when you want it running unattended.
//
// The other rule still stands and this build cannot enforce it: a seated devkit
// with USB live back-feeds 5 V out of J13 through Q1. Either the bench supply
// is on before USB goes in, or J13 is empty.
//
// The panel's 5 V does NOT come from this board. J1-J12 carry DATA + GND only
// (FABRICATION.md, "Panel power stays off this board"). The panel's red lead
// goes to the bench supply, its GND to the supply, and the J1 pair carries data
// and the signal ground.
//
// WHAT "PASS" LOOKS LIKE
//   - Serial banner names the pin map, then a line every time a slider moves.
//   - The panel shows 0, 1, 2 or 3 matching the sliders, in its own colour.
//   - Two blocks on the LEFT edge mirror the two column poles, so you can see
//     which slider you just touched without decoding the digit.
//   - Two blocks on the RIGHT edge are the spare poles, GPIO 17 and 18. They
//     are wired and routed but nothing reads them in production; they are here
//     so the traces get exercised once before anyone relies on them.
//
// A dark panel with a healthy serial banner is power, data or the panel - not
// the firmware. That is the whole point of printing before lighting anything.

#include <Arduino.h>
#include <FastLED.h>

// ------------------------------------------------------------------ pins ----
// D1 on the production board: GPIO 4 -> R1 (330R) -> U1 -> J1.
#ifndef LED_PIN
#define LED_PIN 4
#endif
// Both SN74AHCT245s share /OE. HIGH = high-impedance and the panels see a
// defined low through R16-R27; the board pulls it up, so it is already safe at
// reset. Nothing reaches a panel until this goes LOW.
#ifndef OE_PIN
#define OE_PIN 8
#endif

// Column select, rev B. Confirmed against hw/gen_sch.py: devkit pad 15 = GPIO 9
// = COL_B0, pad 9 = GPIO 16 = COL_B1, pad 10 = GPIO 17, pad 11 = GPIO 18.
// Every pole's common side is GND, so the internal pull-up makes an OPEN switch
// read 1 and a CLOSED switch read 0 - and the firmware inverts. Closed = 1.
#define PIN_COL_B0  9    // silkscreen "1", binary weight 1
#define PIN_COL_B1  16   // silkscreen "2", binary weight 2
#define PIN_COL_SP0 17   // silkscreen "SP", unread in production
#define PIN_COL_SP1 18   // silkscreen "SP", unread in production

#define PANEL_W 16
#define PANEL_H 16
#ifndef PANEL_LEDS
#define PANEL_LEDS (PANEL_W * PANEL_H)
#endif

// One panel of a digit is roughly 90 LEDs. At full white that would be 5.4 A,
// which is not what anyone wants on a bench with a meter on it. FastLED rescales
// the whole frame to stay inside MAX_MA, so a mistake dims the panel instead of
// browning out the supply.
#ifndef BRIGHTNESS
#define BRIGHTNESS 80
#endif
#ifndef MAX_MA
#define MAX_MA 1500
#endif

// 1 = drive /OE low as soon as the first frame is buffered, with no prompt.
// Only for a panel you know is powered, or a bench with nothing on J1.
#ifndef AUTO_ENABLE
#define AUTO_ENABLE 0
#endif

static CRGB leds[PANEL_LEDS];

// ---------------------------------------------------------------- mapping ---
// Column-serpentine, the same formula the driver and wall.yaml agree on:
//   local = x * 16 + (y if x even else 15 - y)
// x is 0..15 left to right, y is 0..15 top to bottom. If the digit comes out
// mirrored in alternate columns, THIS is wrong for your panels, not the glyphs.
static inline uint16_t px(uint8_t x, uint8_t y) {
    return (uint16_t)x * PANEL_H + ((x & 1) ? (PANEL_H - 1 - y) : y);
}

static inline void put(uint8_t x, uint8_t y, const CRGB &c) {
    if (x < PANEL_W && y < PANEL_H) leds[px(x, y)] = c;
}

static void block(uint8_t x0, uint8_t y0, uint8_t w, uint8_t h, const CRGB &c) {
    for (uint8_t y = 0; y < h; y++)
        for (uint8_t x = 0; x < w; x++) put(x0 + x, y0 + y, c);
}

// ----------------------------------------------------------------- glyphs ---
// Four digits, 10 wide x 12 tall, drawn as one bitmask per row with bit 9 at
// the LEFT. Placed at x=3, y=2, which leaves x 0-2 and 13-15 clear for the
// switch indicators and y 0-1 / 14-15 clear at top and bottom.
#define GLYPH_W 10
#define GLYPH_H 12
#define GLYPH_X 3
#define GLYPH_Y 2

static const uint16_t GLYPH[4][GLYPH_H] = {
    // 0
    {0x0FC, 0x1FE, 0x387, 0x303, 0x303, 0x303,
     0x303, 0x303, 0x303, 0x387, 0x1FE, 0x0FC},
    // 1
    {0x030, 0x070, 0x0F0, 0x1F0, 0x030, 0x030,
     0x030, 0x030, 0x030, 0x030, 0x1FE, 0x1FE},
    // 2
    {0x0FC, 0x1FE, 0x303, 0x003, 0x006, 0x00C,
     0x018, 0x030, 0x060, 0x0C0, 0x3FF, 0x3FF},
    // 3
    {0x0FC, 0x1FE, 0x303, 0x003, 0x006, 0x07C,
     0x07C, 0x006, 0x003, 0x303, 0x1FE, 0x0FC},
};

// One colour per column, so the panel is readable from across the room before
// the digit resolves. The DIGIT is the real signal; colour is redundant on
// purpose, because "which green did you mean" is not a bring-up conversation.
static const CRGB COL_RGB[4] = {
    CRGB(255,  24,   0),   // 0  red
    CRGB(255, 120,   0),   // 1  amber
    CRGB(  0, 220,  40),   // 2  green
    CRGB( 40, 110, 255),   // 3  blue
};
static const char *COL_NAME[4] = {"red", "amber", "green", "blue"};

// ------------------------------------------------------------------ state ---
static bool g_live = false;     // have the level shifters been enabled yet
static void enableOutputs();

struct Switches { bool b0, b1, sp0, sp1; uint8_t col; };

static Switches readSwitches() {
    // Closed pulls to GND, so an OPEN pin reads HIGH. Invert: closed = true = 1.
    Switches s;
    s.b0  = !digitalRead(PIN_COL_B0);
    s.b1  = !digitalRead(PIN_COL_B1);
    s.sp0 = !digitalRead(PIN_COL_SP0);
    s.sp1 = !digitalRead(PIN_COL_SP1);
    s.col = (uint8_t)((s.b1 ? 2 : 0) | (s.b0 ? 1 : 0));
    return s;
}

static void draw(const Switches &s) {
    fill_solid(leds, PANEL_LEDS, CRGB::Black);

    const CRGB on = COL_RGB[s.col];
    for (uint8_t gy = 0; gy < GLYPH_H; gy++) {
        const uint16_t row = GLYPH[s.col][gy];
        for (uint8_t gx = 0; gx < GLYPH_W; gx++)
            if (row & (1u << (GLYPH_W - 1 - gx)))
                put(GLYPH_X + gx, GLYPH_Y + gy, on);
    }

    // Left edge: the two column poles, in the column's own colour when closed
    // and a dim grey when open. Weight 2 above weight 1, matching the silkscreen
    // reading down the switch.
    const CRGB off = CRGB(10, 10, 10);
    block(0, 9,  2, 2, s.b1 ? on : off);    // pole 2, weight 2
    block(0, 12, 2, 2, s.b0 ? on : off);    // pole 1, weight 1

    // Right edge: the spare poles. White, because they mean nothing yet.
    const CRGB spare = CRGB(140, 140, 140);
    block(14, 9,  2, 2, s.sp0 ? spare : off);
    block(14, 12, 2, 2, s.sp1 ? spare : off);
}

static void report(const Switches &s) {
    Serial.printf(
        "column %u (%s)   poles: [2]=%s [1]=%s   spares: SP0=%s SP1=%s   "
        "raw gpio16=%d gpio9=%d gpio17=%d gpio18=%d\n",
        s.col, COL_NAME[s.col],
        s.b1 ? "ON " : "off", s.b0 ? "ON " : "off",
        s.sp0 ? "ON " : "off", s.sp1 ? "ON " : "off",
        digitalRead(PIN_COL_B1), digitalRead(PIN_COL_B0),
        digitalRead(PIN_COL_SP0), digitalRead(PIN_COL_SP1));
}

static void banner() {
    Serial.println();
    Serial.println("=== Baybasi rev B bring-up: one panel + column DIP ===");
    Serial.printf("  panel out   D1  -> GPIO %d -> R1 -> U1 -> J1\n", LED_PIN);
    Serial.printf("  /OE         GPIO %d, LOW enables both 245s\n", OE_PIN);
    Serial.printf("  col bit 0   GPIO %d   silkscreen \"1\", weight 1\n", PIN_COL_B0);
    Serial.printf("  col bit 1   GPIO %d   silkscreen \"2\", weight 2\n", PIN_COL_B1);
    Serial.printf("  spares      GPIO %d, %d   silkscreen \"SP\"\n",
                  PIN_COL_SP0, PIN_COL_SP1);
    Serial.println("  switch CLOSED (ON, toward the GND pads) = 1");
    Serial.println();
    Serial.println("  [2] [1]  column        [2] [1]  column");
    Serial.println("  off off    0           ON  off    2");
    Serial.println("  off ON     1           ON  ON     3");
    Serial.println();
    Serial.printf("  brightness %d/255, capped at %d mA\n", BRIGHTNESS, MAX_MA);
    Serial.println("  panel 5 V comes from the bench supply, never from J1.");
    Serial.println();
}

// ------------------------------------------------------------------- main ---
void setup() {
    // FIRST, before anything else can touch GPIO 8. The board's 10k to 3V3E
    // already holds it high through reset; this makes sure nothing pulls it low
    // by accident while the frame buffer is still full of whatever was in RAM.
    pinMode(OE_PIN, OUTPUT);
    digitalWrite(OE_PIN, HIGH);

    Serial.begin(115200);
    // Native USB CDC needs a moment to enumerate, and losing the banner on a
    // bring-up board is a genuine cost. Bounded so it never waits forever if
    // nobody is watching - this thing is meant to run unattended too.
    const uint32_t t0 = millis();
    while (!Serial && millis() - t0 < 2000) delay(10);
    banner();

    pinMode(PIN_COL_B0,  INPUT_PULLUP);
    pinMode(PIN_COL_B1,  INPUT_PULLUP);
    pinMode(PIN_COL_SP0, INPUT_PULLUP);
    pinMode(PIN_COL_SP1, INPUT_PULLUP);
    delay(5);                       // let the internal pull-ups settle

    FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, PANEL_LEDS);
    FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MA);
    FastLED.setBrightness(BRIGHTNESS);

    // Compose and clock out one complete frame with the shifters still
    // high-impedance, exactly as the production firmware does, so the panel
    // never shows the garbage that was in the buffer at reset. With /OE high
    // this goes nowhere, which is the point.
    draw(readSwitches());
    FastLED.show();

    report(readSwitches());
    Serial.println();
    Serial.println("PHASE 1: /OE is HIGH. The panel is isolated and dark.");
    Serial.println("Flip the sliders now - the switch readout works with the");
    Serial.println("panel unpowered, because it is pure GPIO.");
    Serial.println();
#if AUTO_ENABLE
    enableOutputs();
#else
    Serial.println(">>> Power the panel, then press ENTER to enable outputs. <<<");
#endif
}

static void enableOutputs() {
    if (g_live) return;
    digitalWrite(OE_PIN, LOW);
    g_live = true;
    Serial.println();
    Serial.println("PHASE 2: /OE LOW. The panel is live.");
}

void loop() {
    // POLLED, deliberately. Production reads the switches ONCE at boot - a
    // column is not a runtime setting and a reboot is the honest way to apply
    // one. Here we poll so you can flip a slider and watch the digit follow,
    // which is the entire point of this build. Do not copy this into ../fw.
    static Switches last = {false, false, false, false, 255};
    static uint32_t lastBeat = 0;

    // Any byte from the monitor releases the gate. Deliberately any byte and
    // not a specific key: at the bench you have one hand on a supply.
    if (!g_live && Serial.available()) {
        while (Serial.available()) Serial.read();
        enableOutputs();
    }

    const Switches s = readSwitches();
    const bool changed = s.b0 != last.b0 || s.b1 != last.b1 ||
                         s.sp0 != last.sp0 || s.sp1 != last.sp1;

    if (changed) {
        draw(s);
        // Harmless while /OE is high - the bits go out of the GPIO and stop at
        // the shifters - and it keeps the buffer correct for the moment it
        // is not.
        FastLED.show();
        report(s);
        last = s;
    } else if (millis() - lastBeat > 5000) {
        // Proof of life with nothing moving, so a silent monitor means a hung
        // board rather than a switch nobody is touching.
        lastBeat = millis();
        report(s);
        if (!g_live)
            Serial.println("  (outputs still gated - press ENTER once the panel has 5 V)");
    }

    delay(50);
}
