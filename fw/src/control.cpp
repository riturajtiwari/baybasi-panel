#include "control.h"
#include <AsyncUDP.h>
#include <ETH.h>
#include "config.h"
#include "ddp.h"
#include "framebuf.h"
#include "identity.h"
#include "net.h"
#include "status.h"

namespace {

AsyncUDP g_udp;
uint32_t g_lastAnnounce = 0;

volatile bool g_otaPending = false;
String g_otaUrl, g_otaSha;

// A tiny JSON field reader.  Bringing in a JSON library to parse six known keys
// from a message we also write is not worth the flash or the attack surface.
String field(const String &doc, const char *key) {
    String needle = String("\"") + key + "\"";
    int k = doc.indexOf(needle);
    if (k < 0) return String();
    k = doc.indexOf(':', k + needle.length());
    if (k < 0) return String();
    k++;
    while (k < (int)doc.length() && isspace((unsigned char)doc[k])) k++;
    if (k >= (int)doc.length()) return String();
    if (doc[k] == '"') {
        const int end = doc.indexOf('"', k + 1);
        return end < 0 ? String() : doc.substring(k + 1, end);
    }
    int end = k;
    while (end < (int)doc.length() && doc[end] != ',' && doc[end] != '}') end++;
    String v = doc.substring(k, end);
    v.trim();
    return v;
}

uint32_t ipToU32(const String &s) {
    IPAddress a;
    return a.fromString(s) ? (uint32_t)a : 0;
}

void ack(const char *of, bool ok) {
    char buf[128];
    snprintf(buf, sizeof(buf), "{\"t\":\"ack\",\"mac\":\"%s\",\"of\":\"%s\","
             "\"ok\":%s}", identity::macString(), of, ok ? "true" : "false");
    g_udp.broadcastTo((uint8_t *)buf, strlen(buf), CTRL_PORT);
}

void onPacket(AsyncUDPPacket &pkt) {
    if (pkt.length() < 8 || pkt.length() > 1024) return;
    String doc((const char *)pkt.data(), pkt.length());

    // Every command names its target MAC, so a broadcast command reaches only
    // the board it is meant for.  Our own announcements are ignored here.
    const String mac = field(doc, "mac");
    if (!mac.equalsIgnoreCase(identity::macString())) return;

    const String t = field(doc, "t");

    if (t == "assign") {
        const String col = field(doc, "col");
        if (col.isEmpty() || col == "null") {
            identity::clear();
            ack("assign", true);
            log_w("column cleared by the Pi; rebooting to take DHCP");
            delay(150);
            ESP.restart();
            return;
        }
        const int column = col.toInt();
        const uint32_t ip = ipToU32(field(doc, "ip"));
        const uint32_t gw = ipToU32(field(doc, "gw"));
        const uint32_t mask = ipToU32(field(doc, "mask"));
        const int ddpId = field(doc, "ddp_id").toInt();
        const int pixels = field(doc, "pixels").toInt();
        const bool ok = identity::assign(
            (int8_t)column, ip, gw, mask,
            (uint8_t)(ddpId > 0 ? ddpId : 1),
            (uint16_t)(pixels > 0 ? pixels : NUM_LEDS));
        ack("assign", ok);
        // The address changes, so restart rather than try to renumber a live
        // interface.  Commissioning is a one-time act; a clean boot is cheaper
        // than a subtle half-configured state.
        log_i("assigned column %d, rebooting", column);
        delay(150);
        ESP.restart();
        return;
    }

    if (t == "identify") {
        const int secs = field(doc, "s").toInt();
        status::identify((uint32_t)max(1, secs) * 1000);
        ack("identify", true);
        // Worth a line. Without it the only evidence identify ran is a dip in
        // the acquire() null counter, which is a poor thing to have to infer
        // from when someone is asking "did that board answer or not".
        log_i("identify for %d s: flooding all %d outputs at level %u",
              max(1, secs), NUM_OUTPUTS, (unsigned)IDENTIFY_LEVEL);
        return;
    }

    if (t == "reboot") {
        ack("reboot", true);
        delay(150);
        ESP.restart();
        return;
    }

    if (t == "ota") {
        g_otaUrl = field(doc, "url");
        g_otaSha = field(doc, "sha256");
        if (g_otaUrl.isEmpty()) { ack("ota", false); return; }
        g_otaPending = true;      // the main loop does the work
        ack("ota", true);
        return;
    }
}

}  // namespace

namespace control {

bool begin() {
    if (!g_udp.listen(CTRL_PORT)) {
        log_e("cannot listen on udp/%u", CTRL_PORT);
        return false;
    }
    g_udp.onPacket(onPacket);
    log_i("control plane on udp/%u", CTRL_PORT);
    return true;
}

void tick() {
    const uint32_t now = millis();
    if (now - g_lastAnnounce < ANNOUNCE_MS) return;
    g_lastAnnounce = now;
    if (!net::linkUp()) return;

    const Identity &id = identity::get();
    char buf[288];
    if (id.assigned()) {
        snprintf(buf, sizeof(buf),
                 "{\"t\":\"announce\",\"mac\":\"%s\",\"col\":%d,\"fw\":\"%s\","
                 "\"up\":%lu,\"frames\":%lu,\"torn\":%lu,\"gaps\":%lu,"
                 "\"link\":true,\"ip\":\"%s\"}",
                 identity::macString(), (int)id.column, FW_VERSION,
                 (unsigned long)(now / 1000), (unsigned long)frames.frames(),
                 (unsigned long)frames.torn(),
                 (unsigned long)ddp::stats().sequenceGaps,
                 net::localIP().toString().c_str());
    } else {
        // No column yet.  This is the message the operator is waiting to see.
        snprintf(buf, sizeof(buf),
                 "{\"t\":\"announce\",\"mac\":\"%s\",\"col\":null,\"fw\":\"%s\","
                 "\"up\":%lu,\"link\":true,\"ip\":\"%s\"}",
                 identity::macString(), FW_VERSION,
                 (unsigned long)(now / 1000),
                 net::localIP().toString().c_str());
    }
    g_udp.broadcastTo((uint8_t *)buf, strlen(buf), CTRL_PORT);
}

bool otaRequested(String &url, String &sha) {
    if (!g_otaPending) return false;
    g_otaPending = false;
    url = g_otaUrl;
    sha = g_otaSha;
    return true;
}

}  // namespace control
