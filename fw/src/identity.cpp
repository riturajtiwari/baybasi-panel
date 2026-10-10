#include "identity.h"
#include <Preferences.h>
#include <esp_mac.h>
#include <IPAddress.h>

namespace {
Identity g_id;
Preferences g_prefs;
char g_mac[18] = {0};
uint8_t g_macBytes[6] = {0};

#if COLUMN_DIP
// SW1, read once. See the column-select block in config.h for the table.
int8_t readColumnSwitch(bool &pole2, bool &pole1) {
    pinMode(PIN_COL_B0, INPUT_PULLUP);
    pinMode(PIN_COL_B1, INPUT_PULLUP);
    // The internal pull-ups have a few picofarads of trace to charge; this is
    // a thousand time constants and costs nothing at boot.
    delayMicroseconds(200);
    // Closed pulls to GND, so an OPEN pole reads HIGH. Invert: closed = 1.
    pole1 = !digitalRead(PIN_COL_B0);
    pole2 = !digitalRead(PIN_COL_B1);
    return (int8_t)((pole2 ? 2 : 0) | (pole1 ? 1 : 0));
}
#endif
}  // namespace

namespace identity {

void begin() {
    esp_read_mac(g_macBytes, ESP_MAC_ETH);
    snprintf(g_mac, sizeof(g_mac), "%02x:%02x:%02x:%02x:%02x:%02x",
             g_macBytes[0], g_macBytes[1], g_macBytes[2],
             g_macBytes[3], g_macBytes[4], g_macBytes[5]);

    // Not fatal on a switch board, which needs nothing from NVS - so no early
    // return until we know which kind of board this is.
    const bool nvsOpen = g_prefs.begin(NVS_NAMESPACE, false);
    if (!nvsOpen) log_e("NVS open failed");

#if COLUMN_DIP
    bool pole2 = false, pole1 = false;
    const int8_t col = readColumnSwitch(pole2, pole1);
    // The same /24 as the commissioning fallback: the pixel segment, with the
    // Pi at .1 as the gateway.
    const IPAddress ip(FALLBACK_NET[0], FALLBACK_NET[1], FALLBACK_NET[2],
                       (uint8_t)(COL_IP_BASE + col));
    const IPAddress gw(FALLBACK_GW[0], FALLBACK_GW[1], FALLBACK_GW[2],
                       FALLBACK_GW[3]);
    const IPAddress mask(FALLBACK_MASK[0], FALLBACK_MASK[1], FALLBACK_MASK[2],
                         FALLBACK_MASK[3]);
    g_id.column  = col;
    g_id.ip      = (uint32_t)ip;
    g_id.gateway = (uint32_t)gw;
    g_id.netmask = (uint32_t)mask;
    g_id.ddpId   = (uint8_t)(COL_DDP_BASE + col);
    g_id.pixels  = NUM_LEDS;
    g_id.source  = Identity::Source::Dip;
    log_i("column %d from SW1 (pole \"2\" %s, pole \"1\" %s) -> %s, ddp id %u",
          (int)col, pole2 ? "ON" : "off", pole1 ? "ON" : "off",
          ip.toString().c_str(), g_id.ddpId);

    // A board commissioned before it had a switch may still carry an NVS
    // column. The switch wins; saying so means a disagreement is a log line
    // rather than a mystery.
    if (nvsOpen) {
        const int8_t stale = (int8_t)g_prefs.getChar("col", COLUMN_UNASSIGNED);
        if (stale != COLUMN_UNASSIGNED && stale != col)
            log_w("NVS still holds column %d from an earlier commissioning; "
                  "ignored - the switch says %d", (int)stale, (int)col);
    }
#else
    if (!nvsOpen) {
        log_e("this board cannot remember its column");
        return;
    }
    g_id.column  = (int8_t)g_prefs.getChar("col", COLUMN_UNASSIGNED);
    g_id.ip      = g_prefs.getUInt("ip", 0);
    g_id.gateway = g_prefs.getUInt("gw", 0);
    g_id.netmask = g_prefs.getUInt("mask", 0);
    g_id.ddpId   = (uint8_t)g_prefs.getUChar("ddp", 1);
    g_id.pixels  = (uint16_t)g_prefs.getUShort("px", NUM_LEDS);
    if (g_id.pixels == 0 || g_id.pixels > NUM_LEDS) g_id.pixels = NUM_LEDS;
    if (g_id.assigned()) g_id.source = Identity::Source::Nvs;
#endif

    log_i("identity: mac=%s column=%d src=%s ddp_id=%u pixels=%u", g_mac,
          (int)g_id.column, sourceName(), g_id.ddpId, g_id.pixels);
}

const Identity &get() { return g_id; }

bool assign(int8_t column, uint32_t ip, uint32_t gw, uint32_t mask,
            uint8_t ddpId, uint16_t pixels) {
    if (pixels == 0 || pixels > NUM_LEDS) pixels = NUM_LEDS;
    bool ok = true;
    ok &= g_prefs.putChar("col", column) > 0 || column == 0;
    ok &= g_prefs.putUInt("ip", ip) > 0 || ip == 0;
    ok &= g_prefs.putUInt("gw", gw) > 0 || gw == 0;
    ok &= g_prefs.putUInt("mask", mask) > 0 || mask == 0;
    ok &= g_prefs.putUChar("ddp", ddpId) > 0;
    ok &= g_prefs.putUShort("px", pixels) > 0;
    g_id = {column, ip, gw, mask, ddpId, pixels, Identity::Source::Nvs};
    log_i("assigned column %d, ip %u.%u.%u.%u, ddp id %u",
          (int)column, ip & 0xff, (ip >> 8) & 0xff, (ip >> 16) & 0xff,
          (ip >> 24) & 0xff, ddpId);
    return ok;
}

bool clear() {
    g_prefs.remove("col");
    g_prefs.remove("ip");
    g_id = Identity{};
    return true;
}

const char *macString() { return g_mac; }

const char *sourceName() {
    switch (g_id.source) {
        case Identity::Source::Dip: return "dip";
        case Identity::Source::Nvs: return "nvs";
        default:                    return "none";
    }
}
void macBytes(uint8_t out[6]) { memcpy(out, g_macBytes, 6); }

}  // namespace identity
