#include "net.h"
#include <ETH.h>
#include <SPI.h>
#include "config.h"
#include "identity.h"

namespace {
bool g_link = false;
uint32_t g_drops = 0;

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
            log_e("static ip config rejected; falling back to DHCP");
        }
    } else {
        log_w("no column assigned: taking DHCP so the Pi can commission this "
              "board (mac %s)", identity::macString());
    }
    return true;
}

bool linkUp() { return g_link && ETH.linkUp(); }
IPAddress localIP() { return ETH.localIP(); }
const char *macString() { return identity::macString(); }
uint32_t linkDrops() { return g_drops; }

void tick() {}

}  // namespace net
