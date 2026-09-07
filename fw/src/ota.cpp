#include "ota.h"
#include <HTTPClient.h>
#include <NetworkClient.h>
#include <Update.h>
#include <mbedtls/sha256.h>
#include "leds.h"
#include "status.h"

namespace {
bool g_busy = false;
String g_error;

String toHex(const uint8_t *d, size_t n) {
    static const char *hex = "0123456789abcdef";
    String s;
    s.reserve(n * 2);
    for (size_t i = 0; i < n; i++) {
        s += hex[d[i] >> 4];
        s += hex[d[i] & 0x0f];
    }
    return s;
}
}  // namespace

namespace ota {

bool inProgress() { return g_busy; }
const char *lastError() { return g_error.c_str(); }

bool update(const String &url, const String &expectedSha256) {
    if (g_busy) return false;
    g_busy = true;
    g_error = "";
    status::set(status::State::Updating);

    // Blank the wall for the duration.  An update takes seconds and a frozen
    // picture during it is indistinguishable from a crash.
    leds::waitDone();
    leds::disableOutputs();

    HTTPClient http;
    NetworkClient client;
    bool ok = false;

    do {
        if (!http.begin(client, url)) { g_error = "bad url"; break; }
        http.setTimeout(20000);
        const int code = http.GET();
        if (code != HTTP_CODE_OK) {
            g_error = "http " + String(code);
            break;
        }
        const int total = http.getSize();
        if (total <= 0) { g_error = "server sent no content length"; break; }
        if (!Update.begin((size_t)total)) {
            g_error = "no room in the other app slot: " +
                      String(Update.errorString());
            break;
        }

        mbedtls_sha256_context sha;
        mbedtls_sha256_init(&sha);
        mbedtls_sha256_starts(&sha, 0);

        NetworkClient *stream = http.getStreamPtr();
        uint8_t buf[1460];
        int written = 0;
        uint32_t idle = millis();
        while (written < total) {
            const size_t avail = stream->available();
            if (!avail) {
                if (millis() - idle > 15000) { g_error = "download stalled"; break; }
                delay(1);
                continue;
            }
            idle = millis();
            const int n = stream->readBytes(buf, min(avail, sizeof(buf)));
            if (n <= 0) continue;
            if (Update.write(buf, n) != (size_t)n) {
                g_error = String("flash write failed: ") + Update.errorString();
                break;
            }
            mbedtls_sha256_update(&sha, buf, n);
            written += n;
            status::tick();
        }

        uint8_t digest[32];
        mbedtls_sha256_finish(&sha, digest);
        mbedtls_sha256_free(&sha);

        if (written != total) {
            if (g_error.isEmpty())
                g_error = "short download: " + String(written) + "/" + String(total);
            Update.abort();
            break;
        }

        const String got = toHex(digest, sizeof(digest));
        if (expectedSha256.length() == 64 && !got.equalsIgnoreCase(expectedSha256)) {
            g_error = "sha256 mismatch, image rejected";
            log_e("ota: expected %s got %s", expectedSha256.c_str(), got.c_str());
            Update.abort();
            break;
        }

        // Only now is the new slot marked bootable.
        if (!Update.end(true)) {
            g_error = String("commit failed: ") + Update.errorString();
            break;
        }
        log_i("ota ok, %d bytes, sha256 %s, rebooting", written, got.c_str());
        ok = true;
    } while (false);

    http.end();
    g_busy = false;

    if (!ok) {
        log_e("ota failed: %s", g_error.c_str());
        status::set(status::State::Fault);
        return false;
    }
    delay(200);
    ESP.restart();
    return true;
}

}  // namespace ota
