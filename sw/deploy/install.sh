#!/usr/bin/env bash
# Install the Baybasi wall software on a headless Pi OS Lite.
#
# Run once per Pi, as root.  Idempotent.
set -euo pipefail

PREFIX=/opt/baybasi
DATA=/var/lib/baybasi
IFACE=${IFACE:-eth0}
PI_IP=${PI_IP:-192.168.50.1}
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "== packages"
apt-get update -qq
apt-get install -y --no-install-recommends python3 python3-venv ffmpeg chrony

echo "== user and directories"
id -u baybasi >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin baybasi
install -d -o baybasi -g baybasi "$DATA" "$DATA/media" "$DATA/cache" "$DATA/firmware"
install -d "$PREFIX"
cp -r "$SRC/baybasi" "$SRC/config" "$SRC/pyproject.toml" "$PREFIX/"

echo "== virtualenv"
python3 -m venv "$PREFIX/.venv"
"$PREFIX/.venv/bin/pip" install --upgrade pip -q
"$PREFIX/.venv/bin/pip" install -q "$PREFIX"

echo "== pixel network on $IFACE -> $PI_IP"
# Static, and NEVER the default route.  The LED network has no way out, and if
# it becomes the default route the Pi loses DNS and NTP - and NTP is the only
# thing keeping the two displays in step.
nmcli connection show pixelnet >/dev/null 2>&1 || \
    nmcli connection add type ethernet ifname "$IFACE" con-name pixelnet
nmcli connection modify pixelnet \
    ipv4.method manual \
    ipv4.addresses "$PI_IP/24" \
    ipv4.never-default yes \
    ipv6.method disabled \
    connection.autoconnect yes
nmcli connection up pixelnet || true

echo "== time"
# Both displays derive the frame index from wall-clock time against a shared
# epoch.  If the clocks drift apart, the walls drift apart.
timedatectl set-ntp true || true
systemctl enable --now chrony || true

echo "== services"
install -m644 "$SRC/deploy/baybasi-driver.service" /etc/systemd/system/
install -m644 "$SRC/deploy/baybasi-web.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now baybasi-web.service
systemctl enable --now baybasi-driver.service

echo
echo "installed."
echo "  upload utility : http://$PI_IP:8080  (and on this Pi's other address)"
echo "  driver log     : journalctl -u baybasi-driver -f"
echo "  wall config    : $PREFIX/config/wall.yaml"
echo
echo "Check the clock before you trust the two walls to stay in step:"
echo "  chronyc tracking"
