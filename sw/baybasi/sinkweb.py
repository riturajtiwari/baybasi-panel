"""Browser viewer for the software sink: MJPEG stream plus live protocol stats.

Stdlib only, so the sink stays runnable on a bare Pi or a laptop with nothing
but NumPy and Pillow installed.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import numpy as np

from .geometry import Wall
from .sink import DDPSink, frame_to_png

PAGE = """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Baybasi DDP sink</title>
<style>
 :root{color-scheme:dark;--bg:#0b0d10;--fg:#e6e9ee;--dim:#8b93a1;--ok:#4ade80;--bad:#f87171;--warn:#fbbf24;--line:#1e242c}
 body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
 .wrap{display:flex;gap:24px;padding:20px;flex-wrap:wrap;align-items:flex-start}
 .screen{background:#000;border:1px solid var(--line);border-radius:6px;padding:8px;position:relative}
 img{display:block;image-rendering:pixelated;border-radius:2px}
 h1{font-size:15px;margin:0 0 12px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
 table{border-collapse:collapse;font-size:13px}
 td,th{padding:3px 12px 3px 0;text-align:left;vertical-align:top}
 th{color:var(--dim);font-weight:400}
 .num{font-variant-numeric:tabular-nums}
 .ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)}
 #notes:not(:empty){margin:0 0 14px;padding:10px 12px;border-radius:8px;
      background:#2a1a06;border:1px solid #7c4a03;color:#fcd34d;font-size:13px;max-width:560px}
 #notes div+div{margin-top:6px}
 #log{margin-top:16px;max-width:560px;max-height:220px;overflow:auto;font-size:12px;
      background:#12161b;border:1px solid var(--line);border-radius:6px;padding:10px;color:var(--warn)}
 label{color:var(--dim);font-size:13px;margin-right:14px;cursor:pointer}
 .panel{min-width:340px}
</style>
<div class="wrap">
  <div class="screen"><img id="wall" src="/stream.mjpg?grid=0" width="256" height="768" alt="wall"></div>
  <div class="panel">
    <h1>DDP sink &middot; 64 &times; 192</h1>
    <div id="notes"></div>
    <div style="margin-bottom:12px">
      <label><input type="checkbox" id="grid"> panel grid</label>
      <label><input type="checkbox" id="big"> 2&times;</label>
    </div>
    <table id="top"></table>
    <h1 style="margin-top:18px">Controllers</h1>
    <table id="ctrl"></table>
    <div id="log"></div>
  </div>
</div>
<script>
const $=s=>document.querySelector(s);
const img=$('#wall');
function src(){img.src='/stream.mjpg?grid='+($('#grid').checked?1:0)+'&t='+Date.now();}
$('#grid').onchange=src;
$('#big').onchange=()=>{const b=$('#big').checked;img.width=b?512:256;img.height=b?1536:768;};
function cls(n,good){return n>0?(good?'ok':'bad'):'';}
async function poll(){
 try{
  const s=await (await fetch('/status.json')).json();
  $('#top').innerHTML=[
    ['frames',s.frames],['fps',s.fps.toFixed(2)],['packets',s.packets],
    ['pushes',s.pushes],
    ['torn frames','<span class="'+cls(s.torn,false)+'">'+s.torn+'</span>'],
    ['violations','<span class="'+cls(s.violations,false)+'">'+s.violations+'</span>'],
    ['unattributed','<span class="'+cls(s.unattributed,false)+'">'+s.unattributed+'</span>'],
  ].map(r=>'<tr><th>'+r[0]+'</th><td class="num">'+r[1]+'</td></tr>').join('');
  $('#ctrl').innerHTML='<tr><th>col</th><th>ip</th><th>id</th><th>frames</th><th>torn</th><th>gaps</th><th>age</th></tr>'+
    s.controllers.map(c=>'<tr><td>'+c.column+'</td><td>'+c.ip+'</td><td>'+c.ddp_id+'</td>'+
      '<td class="num">'+c.frames+'</td><td class="num '+cls(c.torn,false)+'">'+c.torn+'</td>'+
      '<td class="num '+cls(c.seq_gaps,false)+'">'+c.seq_gaps+'</td>'+
      '<td class="num">'+(c.age_ms==null?'-':(c.age_ms>500?'<span class="bad">'+c.age_ms+'ms</span>':c.age_ms+'ms'))+'</td></tr>').join('');
  $('#notes').innerHTML=(s.notes||[]).map(n=>'<div>&#9888; '+n.replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))+'</div>').join('');
  const lg=await (await fetch('/log.json')).json();
  $('#log').innerHTML=lg.length?lg.map(l=>'<div>'+l.replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))+'</div>').join(''):'<span style="color:#4ade80">no protocol violations</span>';
 }catch(e){}
 setTimeout(poll,500);
}
poll();
</script>
"""


class SinkWeb:
    """Holds the newest frame and serves it as an MJPEG stream."""

    def __init__(self, sink: DDPSink, wall: Wall, *, scale: int = 4,
                 host: str = "0.0.0.0", port: int = 8088, log_size: int = 60):
        self.sink = sink
        self.wall = wall
        self.scale = scale
        self.host, self.port = host, port
        self._frame: Optional[np.ndarray] = np.zeros(
            (wall.height, wall.width, 3), dtype=np.uint8
        )
        self._new = threading.Condition()
        self._seq = 0
        self.log: list[str] = []
        self.log_size = log_size
        self._server: Optional[ThreadingHTTPServer] = None

    # ---- hooks for the sink -------------------------------------------

    def on_frame(self, frame: np.ndarray) -> None:
        with self._new:
            self._frame = frame
            self._seq += 1
            self._new.notify_all()

    def on_violation(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.append(f"{stamp}  {msg}")
        del self.log[: max(0, len(self.log) - self.log_size)]

    # ---- server --------------------------------------------------------

    def _handler(self):
        web = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # keep the console for sink stats
                pass

            def _send(self, code, ctype, body: bytes):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path, _, query = self.path.partition("?")
                params = dict(
                    p.split("=", 1) for p in query.split("&") if "=" in p
                )
                if path in ("/", "/index.html"):
                    self._send(200, "text/html; charset=utf-8", PAGE.encode())
                elif path == "/status.json":
                    self._send(200, "application/json",
                               json.dumps(web.sink.status()).encode())
                elif path == "/log.json":
                    self._send(200, "application/json",
                               json.dumps(web.log[-30:][::-1]).encode())
                elif path == "/frame.png":
                    grid = params.get("grid") == "1"
                    with web._new:
                        frame = web._frame
                    self._send(200, "image/png",
                               frame_to_png(frame, web.scale, grid, web.wall))
                elif path == "/stream.mjpg":
                    self._stream(params.get("grid") == "1")
                else:
                    self._send(404, "text/plain", b"not found")

            def _stream(self, grid: bool):
                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                last = -1
                try:
                    while True:
                        with web._new:
                            if web._seq == last:
                                web._new.wait(1.0)
                            frame, last = web._frame, web._seq
                        png = frame_to_png(frame, web.scale, grid, web.wall)
                        self.wfile.write(b"--frame\r\nContent-Type: image/png\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(png)}\r\n\r\n".encode()
                        )
                        self.wfile.write(png)
                        self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

        return Handler

    def serve_forever(self) -> None:
        self._server = ThreadingHTTPServer((self.host, self.port), self._handler())
        self._server.daemon_threads = True
        self._server.serve_forever()

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, daemon=True, name="sink-web")
        t.start()
        return t

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
