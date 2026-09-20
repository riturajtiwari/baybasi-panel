"""Controller discovery, commissioning and OTA, on UDP 4049.

Port 4048 carries pixels and nothing else.  Everything with a decision in it
happens here, so a control message can never be mistaken for a frame.

Identity, per the handoff, lives in the board's NVS and not in the image: all
four controllers run the same firmware.  An unassigned board announces itself
with its factory MAC; the Pi holds the MAC-to-column table, the same way it
holds every other piece of geometry.  Commissioning a replacement is: plug it
in, watch its MAC appear, tell it which column it is.

Messages are one-line JSON.  Announcements are broadcast by the controller
every 2 s; commands are unicast by the Pi and acknowledged.

    controller -> Pi   {"t":"announce","mac":"...","col":0,"fw":"0.1.0", ...}
    Pi -> controller   {"t":"assign","mac":"...","col":2,"ip":"192.168.50.13"}
    Pi -> controller   {"t":"identify","mac":"..."}          flash the status LED
    Pi -> controller   {"t":"ota","url":"http://192.168.50.1:8080/fw.bin",...}
    controller -> Pi   {"t":"ack","mac":"...","of":"assign","ok":true}
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from .geometry import Wall

log = logging.getLogger("baybasi.control")

ANNOUNCE_TIMEOUT = 8.0     # a board is "gone" after this long without a word


@dataclass
class ControllerInfo:
    mac: str
    ip: str = ""
    column: Optional[int] = None
    fw: str = ""
    uptime_s: float = 0.0
    frames: int = 0
    torn: int = 0
    link: bool = True
    rssi: Optional[int] = None
    last_seen: float = field(default_factory=time.time)
    assigned_column: Optional[int] = None   # what the Pi's table says

    @property
    def age(self) -> float:
        return time.time() - self.last_seen

    @property
    def online(self) -> bool:
        return self.age < ANNOUNCE_TIMEOUT

    @property
    def state(self) -> str:
        if not self.online:
            return "offline"
        if self.column is None:
            return "unassigned"
        if self.assigned_column is not None and self.column != self.assigned_column:
            return "mismatch"
        return "ok"

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(age_s=round(self.age, 1), online=self.online, state=self.state)
        return d


class AssignmentTable:
    """The Pi's MAC-to-column table.  Survives OTA because OTA never sees it."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.map: Dict[str, int] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.map = {
                k.lower(): int(v)
                for k, v in json.loads(self.path.read_text()).items()
            }
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.warning("assignment table %s unreadable: %s", self.path, exc)

    def save(self) -> None:
        from .library import _atomic_write
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.path, json.dumps(self.map, indent=1, sort_keys=True).encode())

    def set(self, mac: str, column: int) -> None:
        mac = mac.lower()
        for other, col in list(self.map.items()):
            if col == column and other != mac:
                log.warning("column %d was %s, now %s", column, other, mac)
                del self.map[other]
        self.map[mac] = int(column)
        self.save()

    def get(self, mac: str) -> Optional[int]:
        return self.map.get(mac.lower())

    def clear(self, mac: str) -> None:
        if self.map.pop(mac.lower(), None) is not None:
            self.save()


class ControlPlane(threading.Thread):
    """Listens for announcements; sends assign / identify / OTA commands."""

    def __init__(self, wall: Wall, *, table_path: Optional[Path] = None,
                 host: str = "0.0.0.0", port: Optional[int] = None,
                 listen: bool = True, ip_lookup=None):
        super().__init__(daemon=True, name="control-plane")
        self.wall = wall
        self.port = port if port is not None else wall.network.control_port
        self.host = host
        # The driver owns the listening socket; the upload utility runs with
        # listen=False and sends commands without competing for the port.
        self.listen = listen
        self._ip_lookup = ip_lookup
        self.table = AssignmentTable(
            table_path or Path("controllers.json")
        )
        self.seen: Dict[str, ControllerInfo] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.sock: Optional[socket.socket] = None
        self.errors: List[str] = []

    # ---- socket --------------------------------------------------------

    def _open(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind((self.host, self.port))
        s.settimeout(0.5)
        return s

    def start(self) -> "ControlPlane":  # type: ignore[override]
        if not self.listen:
            return self
        try:
            self.sock = self._open()
        except OSError as exc:
            # A busy control port must not stop the wall from lighting up.
            log.warning("control plane disabled: cannot bind %s:%d (%s)",
                        self.host, self.port, exc)
            self.errors.append(str(exc))
            return self
        super().start()
        return self

    def run(self) -> None:
        assert self.sock is not None
        while not self._stop.is_set():
            try:
                raw, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            self._on_message(raw, addr[0])

    def stop(self) -> None:
        self._stop.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    # ---- inbound -------------------------------------------------------

    # NOT _handle(). threading.Thread gained a `_handle` attribute in Python
    # 3.13 (a _thread._ThreadHandle, assigned during start()), which shadows a
    # subclass method of that name. The receive thread then dies on its first
    # packet with "'_thread._ThreadHandle' object is not callable" - and
    # `discover`'s screen-clearing output wipes the traceback, so it just looks
    # like nothing is announcing. Works on 3.12, fails on 3.13. Found 2026-09-19.
    def _on_message(self, raw: bytes, src_ip: str) -> None:
        try:
            msg = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return
        if not isinstance(msg, dict):
            return
        kind = msg.get("t")
        mac = str(msg.get("mac", "")).lower()
        if not mac:
            return

        if kind == "announce":
            with self._lock:
                info = self.seen.get(mac) or ControllerInfo(mac=mac)
                info.ip = src_ip
                info.column = msg.get("col") if msg.get("col") is not None else None
                info.fw = str(msg.get("fw", ""))
                info.uptime_s = float(msg.get("up", 0) or 0)
                info.frames = int(msg.get("frames", 0) or 0)
                info.torn = int(msg.get("torn", 0) or 0)
                info.link = bool(msg.get("link", True))
                info.last_seen = time.time()
                info.assigned_column = self.table.get(mac)
                self.seen[mac] = info
            if info.column is None and info.assigned_column is not None:
                # A board that lost its NVS: re-assert what the table says.
                log.info("re-assigning %s to column %d", mac, info.assigned_column)
                self.assign(mac, info.assigned_column)
        elif kind == "ack":
            log.info("ack from %s: %s ok=%s", mac, msg.get("of"), msg.get("ok"))

    # ---- outbound ------------------------------------------------------

    def _send(self, payload: dict, ip: Optional[str] = None) -> bool:
        data = json.dumps(payload, separators=(",", ":")).encode()
        target = ip or self.wall.network.broadcast
        try:
            sock = self.sock
            if sock is None:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                with sock:
                    sock.sendto(data, (target, self.port))
                return True
            sock.sendto(data, (target, self.port))
            return True
        except OSError as exc:
            self.errors.append(f"{target}: {exc}")
            log.warning("control send to %s failed: %s", target, exc)
            return False

    def assign(self, mac: str, column: int) -> bool:
        """Give a board its column.  Persisted on the Pi and in the board's NVS."""
        ctrl = self.wall.controller_by_column(column)
        self.table.set(mac, column)
        with self._lock:
            info = self.seen.get(mac.lower())
            if info:
                info.assigned_column = column
        return self._send(
            {"t": "assign", "mac": mac.lower(), "col": int(column),
             "ip": ctrl.ip, "ddp_id": ctrl.ddp_id,
             "pixels": ctrl.n_pixels,
             "gw": _gateway_of(ctrl.ip), "mask": "255.255.255.0"},
            ip=self._reachable_ip(mac),
        )

    def unassign(self, mac: str) -> bool:
        self.table.clear(mac)
        return self._send({"t": "assign", "mac": mac.lower(), "col": None},
                          ip=self._reachable_ip(mac))

    def identify(self, mac: str, seconds: int = 5) -> bool:
        """Flash a board's status LED, so you can find it behind the panels."""
        return self._send({"t": "identify", "mac": mac.lower(), "s": int(seconds)},
                          ip=self._reachable_ip(mac))

    def reboot(self, mac: str) -> bool:
        return self._send({"t": "reboot", "mac": mac.lower()},
                          ip=self._reachable_ip(mac))

    def ota(self, mac: str, url: str, *, sha256: str = "", version: str = "") -> bool:
        return self._send(
            {"t": "ota", "mac": mac.lower(), "url": url,
             "sha256": sha256, "ver": version},
            ip=self._reachable_ip(mac),
        )

    def _reachable_ip(self, mac: str) -> Optional[str]:
        if self._ip_lookup is not None:
            found = self._ip_lookup(mac.lower())
            if found:
                return found
        with self._lock:
            info = self.seen.get(mac.lower())
        # An unassigned board has a link-local or DHCP address, so we must use
        # whatever address it announced from, not the address it will end up on.
        return info.ip if info and info.ip else None

    # ---- views ---------------------------------------------------------

    def snapshot(self) -> List[dict]:
        with self._lock:
            infos = sorted(
                self.seen.values(),
                key=lambda i: (i.column if i.column is not None else 99, i.mac),
            )
            return [i.as_dict() for i in infos]

    def unassigned(self) -> List[ControllerInfo]:
        with self._lock:
            return [i for i in self.seen.values() if i.online and i.column is None]

    def firmware_report(self) -> str:
        rows = self.snapshot()
        if not rows:
            return "no controllers have announced themselves"
        w = ["col  mac                ip               fw        state     age"]
        for r in rows:
            col = "-" if r["column"] is None else str(r["column"])
            w.append(
                f"{col:<4} {r['mac']:<18} {r['ip']:<16} {r['fw'] or '-':<9} "
                f"{r['state']:<9} {r['age_s']}s"
            )
        return "\n".join(w)


def _gateway_of(ip: str) -> str:
    """The Pi is .1 on the pixel subnet, by the handoff's addressing plan."""
    parts = ip.split(".")
    return ".".join(parts[:3] + ["1"]) if len(parts) == 4 else ""


class FirmwareServer:
    """Serves the OTA image to the controllers over HTTP from the Pi."""

    def __init__(self, firmware_dir: Path, *, host: str = "0.0.0.0", port: int = 8080):
        self.dir = Path(firmware_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.host, self.port = host, port
        self._server = None

    def url_for(self, name: str, pi_ip: str) -> str:
        return f"http://{pi_ip}:{self.port}/{name}"

    def start(self) -> threading.Thread:
        import functools
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(self.dir))
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._server.daemon_threads = True
        t = threading.Thread(target=self._server.serve_forever, daemon=True,
                             name="fw-server")
        t.start()
        log.info("firmware server on %s:%d serving %s", self.host, self.port, self.dir)
        return t

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
