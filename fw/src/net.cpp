#include "net.h"
#include <ETH.h>
#include <SPI.h>
#include "config.h"
#include "identity.h"

namespace {
bool g_link = false;
uint32_t g_drops = 0;

// Set when this board has no static address of its own, so tick() has to
// watch for it having no address and step in.
//
// This is NEVER latched off once an address arrives. The first version of
// this cleared it on the first success, which meant a board that got a lease
// and then lost it - moved to another segment, or a cable pulled for longer
// than the lease survived - sat at 0.0.0.0 for ever with no way back. Caught
// on hardware: the board took a DHCP address on the bench LAN, was moved to a
// segment with no DHCP server, and reported ip=0.0.0.0 indefinitely. In the
// field that is a board that has to be power-cycled by hand to come back,
// which is the failure this whole fallback exists to prevent.
bool g_selfAddressing = false;
uint32_t g_noAddressSince = 0;

IPAddress fallbackAddress() {
    uint8_t mac[6];
    identity::macBytes(mac);
    // TWO bytes of MAC, not one. The low byte alone spreads 256 values over
    // 176 slots, which both wastes most of the range and makes neighbouring
    // boards from one production run - which often differ only in the last
    // byte, consecutively - far more likely to land on top of each other.
    const uint8_t host = fallbackHostByte(mac[4], mac[5]);
    return IPAddress(FALLBACK_NET[0], FALLBACK_NET[1], FALLBACK_NET[2], host);
}

void takeFallbackAddress() {
    static bool warned = false;
    const IPAddress ip = fallbackAddress();
    if (!ETH.config(ip, IPAddress(FALLBACK_GW[0], FALLBACK_GW[1],
                                  FALLBACK_GW[2], FALLBACK_GW[3]),
                    IPAddress(FALLBACK_MASK[0], FALLBACK_MASK[1],
                              FALLBACK_MASK[2], FALLBACK_MASK[3]))) {
        // Once only. A rejected config will be rejected again on every tick,
        // and 8-second log spam buries whatever the real problem is.
        if (!warned) {
            log_e("fallback address %s rejected; this board cannot be "
                  "discovered", ip.toString().c_str());
            warned = true;
        }
        return;
    }
    warned = false;
    log_w("no address for %lu ms: taking %s so the Pi can find and commission "
          "this board", (unsigned long)DHCP_WAIT_MS, ip.toString().c_str());
}

void onEvent(arduino_event_id_t event) {
    switch (event) {
        case ARDUINO_EVENT_ETH_START:
            ETH.setHostname("baybasi-ctrl");
            break;
        case ARDUINO_EVENT_ETH_CONNECTED:
            log_i("ethernet link up");
            break;
        case ARDUINO_EVENT_ETH_GOT_IP:
            log_i("ip %s  mac %s  %s duplex %d Mbps",
                  ETH.localIP().toString().c_str(), ETH.macAddress().c_str(),
                  ETH.fullDuplex() ? "full" : "half", ETH.linkSpeed());
            g_link = true;
            break;
        case ARDUINO_EVENT_ETH_DISCONNECTED:
        case ARDUINO_EVENT_ETH_STOP:
            if (g_link) g_drops++;
            g_link = false;
            log_w("ethernet link down");
            break;
        default:
            break;
    }
}
}  // namespace

namespace net {

bool begin() {
    Network.onEvent(onEvent);

    // Hard-reset the W5500 ourselves so the timing is explicit: the module
    // needs 50 ms after RST is released before SPI is touched, and a module
    // that is talked to too early comes up looking dead.
    pinMode(PIN_ETH_RST, OUTPUT);
    digitalWrite(PIN_ETH_RST, LOW);
    delay(10);
    digitalWrite(PIN_ETH_RST, HIGH);
    delay(50);

    SPI.begin(PIN_ETH_SCK, PIN_ETH_MISO, PIN_ETH_MOSI, PIN_ETH_CS);

    // rst is passed as -1: the reset above has already happened and been
    // waited out, and letting the driver pulse it again would skip that wait.
    // The SPIClass overload takes the bus, not the pins: SPI.begin() above has
    // already bound SCK/MISO/MOSI. The 10-argument form that also takes pins
    // wants a spi_host_device_t in that slot, not an SPIClass, so passing both
    // an SPIClass and the pins matches no overload at all.
    const bool ok = ETH.begin(ETH_PHY_W5500, /*phy_addr=*/1, PIN_ETH_CS,
                              PIN_ETH_INT, /*rst=*/-1, SPI, ETH_SPI_MHZ);
    if (!ok) {
        log_e("ETH.begin failed: check the W5500 module, CS on GPIO%d and the "
              "50 ms reset delay", PIN_ETH_CS);
        return false;
    }

    const Identity &id = identity::get();
    if (id.assigned() && id.ip != 0) {
        if (!ETH.config(IPAddress(id.ip), IPAddress(id.gateway),
                        IPAddress(id.netmask))) {
            log_e("static ip config rejected; falling back to DHCP, then to a "
                  "MAC-derived address");
            g_selfAddressing = true;
        }
    } else {
        // Assigned-but-no-address counts as unassigned for this purpose: it
        // still needs some way to be reached.
        log_w("no address of its own: DHCP first, then a MAC-derived address "
              "on the pixel segment (mac %s)", identity::macString());
        g_selfAddressing = true;
    }
    g_noAddressSince = millis();
    return true;
}

// Deliberately reads the interface rather than trusting g_link. g_link is set
// from ARDUINO_EVENT_ETH_GOT_IP, which never fires for an address we set
// ourselves - so keying "usable" off the event is what kept an unassigned
// board on a DHCP-less segment from ever announcing.
bool linkUp() { return ETH.linkUp() && ETH.hasIP(); }
IPAddress localIP() { return ETH.localIP(); }
const char *macString() { return identity::macString(); }
uint32_t linkDrops() { return g_drops; }

void tick() {
    if (!g_selfAddressing) return;          // has a static address of its own
    // Hold the clock at zero for as long as there IS an address, from DHCP or
    // from us. The moment one goes away the clock starts, and DHCP_WAIT_MS
    // later we take one. This runs for the life of the board, not just at
    // boot, so losing an address is recoverable without a power cycle.
    if (ETH.hasIP()) { g_noAddressSince = millis(); return; }
    if (millis() - g_noAddressSince < DHCP_WAIT_MS) return;
    takeFallbackAddress();
}

}  // namespace net
