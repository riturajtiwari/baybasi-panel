#include "identity.h"
#include <Preferences.h>
#include <esp_mac.h>

namespace {
Identity g_id;
Preferences g_prefs;
char g_mac[18] = {0};
uint8_t g_macBytes[6] = {0};
}  // namespace

namespace identity {

void begin() {
    esp_read_mac(g_macBytes, ESP_MAC_ETH);
    snprintf(g_mac, sizeof(g_mac), "%02x:%02x:%02x:%02x:%02x:%02x",
             g_macBytes[0], g_macBytes[1], g_macBytes[2],
             g_macBytes[3], g_macBytes[4], g_macBytes[5]);

    if (!g_prefs.begin(NVS_NAMESPACE, false)) {
        log_e("NVS open failed; this board cannot remember its column");
        return;
    }
    g_id.column  = (int8_t)g_prefs.getChar("col", COLUMN_UNASSIGNED);
    g_id.ip      = g_prefs.getUInt("ip", 0);
    g_id.gateway = g_prefs.getUInt("gw", 0);
    g_id.netmask = g_prefs.getUInt("mask", 0);
    g_id.ddpId   = (uint8_t)g_prefs.getUChar("ddp", 1);
    g_id.pixels  = (uint16_t)g_prefs.getUShort("px", NUM_LEDS);
    if (g_id.pixels == 0 || g_id.pixels > NUM_LEDS) g_id.pixels = NUM_LEDS;

    log_i("identity: mac=%s column=%d ddp_id=%u pixels=%u",
          g_mac, (int)g_id.column, g_id.ddpId, g_id.pixels);
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
    g_id = {column, ip, gw, mask, ddpId, pixels};
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
void macBytes(uint8_t out[6]) { memcpy(out, g_macBytes, 6); }

}  // namespace identity
