#pragma once
#include <Arduino.h>

// ---------------------------------------------------------------------------
// Baybasi controller: compile-time configuration.
//
// The pin map is final.  It comes from the board's pad coordinates, not from
// preference - see hw/FABRICATION.md.  Nothing here is a suggestion.
// ---------------------------------------------------------------------------

#define FW_VERSION "0.1.0"

// ---- W5500 on SPI ---------------------------------------------------------
static constexpr int PIN_ETH_CS   = 10;   // devkit pad 16, FSPI IOMUX
static constexpr int PIN_ETH_MOSI = 11;   // pad 17
static constexpr int PIN_ETH_SCK  = 12;   // pad 18
static constexpr int PIN_ETH_MISO = 13;   // pad 19
static constexpr int PIN_ETH_INT  = 14;   // pad 20
static constexpr int PIN_ETH_RST  = 15;   // pad 8, active low, 10k to 3V3E
// Overridable so the bench can drop it without editing this file:
//   PLATFORMIO_BUILD_FLAGS="-DETH_SPI_MHZ_CFG=4" pio run
// 25 MHz is well inside the W5500's 33 MHz ceiling, but it crosses two socket
// pairs and a plug-in module, so it is the first thing to lower when SPI reads
// back all zeros.
#ifndef ETH_SPI_MHZ_CFG
#define ETH_SPI_MHZ_CFG 25
#endif
static constexpr int ETH_SPI_MHZ  = ETH_SPI_MHZ_CFG;

// ---- twelve LED outputs, D1 .. D12 ---------------------------------------
// D1-D3 are the left row; D4-D12 the right row.
static constexpr int NUM_OUTPUTS = 12;
static const int LED_PINS[NUM_OUTPUTS] = {
    4, 5, 6,                              // D1  D2  D3
    1, 2, 21, 38, 39, 40, 41, 42, 47,     // D4 .. D12
};

// ---- level shifters -------------------------------------------------------
// GPIO 8 drives /OE on both SN74AHCT245N and is pulled up to 3V3E on the board.
// HIGH = outputs high-impedance, and the panels then see a defined low through
// R16-R27.  It is held high through boot and driven low only once a complete
// frame is buffered, otherwise the wall shows noise at power-up.
static constexpr int PIN_OE = 8;

static constexpr int PIN_SYNC   = 7;      // J14, optional, unpopulated
static constexpr int PIN_STATUS = 48;     // on-board RGB LED

// ---- geometry this board owns --------------------------------------------
// One panel per output, never daisy-chained.  That is what holds a strand to
// 256 LEDs and the frame time to 7.68 ms + 300 us latch = 7.98 ms, so 125 fps.
static constexpr int    PANEL_LEDS  = 256;
static constexpr int    NUM_LEDS    = PANEL_LEDS * NUM_OUTPUTS;   // 3072
static constexpr size_t FRAME_BYTES = (size_t)NUM_LEDS * 3;       // 9216

// ---- wire -----------------------------------------------------------------
static constexpr uint16_t DDP_PORT  = 4048;
static constexpr uint16_t CTRL_PORT = 4049;   // announce / assign / OTA

// After this long with no pixels, fade out.  A frozen wall looks like working
// content and hides the fault.
static constexpr uint32_t SIGNAL_TIMEOUT_MS = 500;
static constexpr uint32_t FADE_MS           = 600;
static constexpr uint32_t ANNOUNCE_MS       = 2000;
static constexpr uint32_t IDLE_REFRESH_MS   = 40;    // keep showing while idle

// ---- colour ---------------------------------------------------------------
// The Pi sends RGB, which is what the DDP data-type byte declares and what any
// third-party DDP tool will assume. This maps each source channel into the
// buffer slot that actually lights the right colour, in framebuf.cpp:
//     dst[px * 3 + CHANNEL_MAP[ch]] = src[ch]
//
// MEASURED ON HARDWARE 2026-09-19, not derived. With the old {1,0,2} map,
// sending pure primaries one at a time to a panel on J1 gave:
//     dst[0] -> green     dst[1] -> BLUE      dst[2] -> RED
// i.e. red and blue were exchanged. {2,0,1} sends each source channel to the
// slot that displays it.
//
// Do not "simplify" this back to a named order like GRB. The value depends on
// FastLED's EOrder handling in the S3 I2S path as well as the panel wiring,
// and reasoning about that chain gave the wrong answer twice. If colours ever
// look wrong again, re-measure: send pure 255,0,0 then 0,255,0 then 0,0,255
// with `baybasi pattern solid --color ...`, ONE AT A TIME, and check first
// that no other sender is running - a stray one costs an afternoon.
static constexpr uint8_t CHANNEL_MAP[3] = {2, 0, 1};   // src R,G,B -> slots

// ---- identity -------------------------------------------------------------
// All four boards run this same image.  Which column a board owns lives in NVS
// and is set at commissioning, so an OTA can never put column 3's identity on
// column 1.
#define NVS_NAMESPACE "baybasi"
static constexpr int8_t COLUMN_UNASSIGNED = -1;
