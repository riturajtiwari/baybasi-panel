"""The upload utility: a small web app on the headless Pi.

Two jobs beyond the obvious ones.

*Preview.*  The wall is 64 x 192 and most photographs are not, so the operator
has to see the crop before it is eight feet tall.  The preview is rendered from
the same decoded cache and through the same gamma/brightness/dither pipeline
the driver uses, so it is not an approximation of the wall - it is the wall's
own bytes, scaled up.

*Two walls, one media set.*  The displays are network-isolated, so the same
media has to be uploaded to each Pi in turn.  The manifest digest on this page
is the check: same digest, same wall.  Paste the other Pi's manifest in and it
names the difference instead of leaving you to find it.
"""

from __future__ import annotations

import io
import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
from flask import (
    Flask, Response, abort, jsonify, render_template, request, send_file,
)
from werkzeug.utils import secure_filename

from .control import ControlPlane
from .driver import read_status
from .geometry import Wall
from .library import Library, LibraryError, compare_manifests
from .media import ALLOWED_EXT, FIT_POLICIES, MediaError
from .pixels import Pipeline

log = logging.getLogger("baybasi.web")

MAX_UPLOAD_MB = 512


def create_app(wall: Wall, library: Library, *, status_dir: Optional[Path] = None,
               table_path: Optional[Path] = None) -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
    app.config["WALL"] = wall
    app.config["LIBRARY"] = library
    app.config["STATUS_DIR"] = Path(status_dir) if status_dir else library.root

    pipeline = Pipeline(wall)

    def driver_status() -> dict:
        return read_status(app.config["STATUS_DIR"]) or {}

    def lookup_ip(mac: str) -> Optional[str]:
        for c in driver_status().get("controllers", []):
            if c.get("mac", "").lower() == mac:
                return c.get("ip")
        return None

    control = ControlPlane(wall, table_path=table_path, listen=False,
                           ip_lookup=lookup_ip)

    # ---- pages ---------------------------------------------------------

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            wall=wall,
            allowed=" ".join(sorted(ALLOWED_EXT)),
            fits=FIT_POLICIES,
            max_mb=MAX_UPLOAD_MB,
        )

    # ---- state ---------------------------------------------------------

    def item_json(item, slot_frames=None):
        return {
            "id": item.id,
            "short": item.id[:12],
            "title": item.display_title,
            "filename": item.filename,
            "kind": item.kind,
            "fit": item.fit,
            "duration": item.duration,
            "enabled": item.enabled,
            "size": item.size,
            "src": f"{item.src_width}x{item.src_height}",
            "src_duration": round(item.src_duration, 2),
            "frames": slot_frames,
        }

    @app.get("/api/state")
    def api_state():
        lib: Library = app.config["LIBRARY"]
        tl = lib.build_timeline()
        frames_by_id = {s.item.id: s.frames for s in tl.slots}
        return jsonify({
            "items": [item_json(i, frames_by_id.get(i.id)) for i in lib.ordered()],
            "manifest": lib.manifest(),
            "driver": driver_status(),
            "wall": {
                "width": wall.width, "height": wall.height,
                "fps": wall.render.fps, "digest": wall.digest,
                "brightness": wall.render.brightness, "gamma": wall.render.gamma,
                "source": str(wall.source_path or ""),
            },
            "version": lib.version,
        })

    @app.get("/api/manifest")
    def api_manifest():
        return jsonify(app.config["LIBRARY"].manifest())

    @app.get("/manifest.json")
    def download_manifest():
        doc = json.dumps(app.config["LIBRARY"].manifest(), indent=2).encode()
        return send_file(
            io.BytesIO(doc), mimetype="application/json", as_attachment=True,
            download_name=f"baybasi-manifest-{time.strftime('%Y%m%d-%H%M')}.json",
        )

    @app.post("/api/compare")
    def api_compare():
        other = request.get_json(silent=True) or {}
        if "manifest" in other:
            other = other["manifest"]
        if not isinstance(other, dict) or "digest" not in other:
            return jsonify({"error": "that does not look like a manifest"}), 400
        mine = app.config["LIBRARY"].manifest()
        diffs = compare_manifests(mine, other)
        return jsonify({
            "match": not diffs,
            "differences": diffs,
            "mine": mine["digest"],
            "theirs": other.get("digest", ""),
        })

    # ---- upload --------------------------------------------------------

    @app.post("/api/upload")
    def api_upload():
        lib: Library = app.config["LIBRARY"]
        fit = request.form.get("fit", "letterbox")
        files = request.files.getlist("file")
        if not files:
            return jsonify({"error": "no file in the request"}), 400
        added, errors = [], []
        tmp_dir = lib.root / "incoming"
        tmp_dir.mkdir(exist_ok=True)
        for fs in files:
            name = secure_filename(fs.filename or "")
            if not name:
                errors.append("a file arrived with no usable name")
                continue
            tmp = tmp_dir / f"{int(time.time() * 1000)}-{name}"
            try:
                fs.save(tmp)
                item = lib.add_file(tmp, filename=name, fit=fit)
                added.append(item_json(item))
            except (LibraryError, MediaError) as exc:
                errors.append(f"{name}: {exc}")
            except Exception as exc:                     # noqa: BLE001
                log.exception("upload of %s failed", name)
                errors.append(f"{name}: {exc}")
            finally:
                tmp.unlink(missing_ok=True)
        code = 200 if added else 400
        return jsonify({"added": added, "errors": errors}), code

    # ---- item mutation -------------------------------------------------

    def _mutate(fn):
        try:
            return jsonify({"ok": True, "item": item_json(fn())})
        except (LibraryError, MediaError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/item/<item_id>/fit")
    def api_fit(item_id):
        fit = (request.get_json(silent=True) or {}).get("fit", "")
        return _mutate(lambda: app.config["LIBRARY"].set_fit(item_id, fit))

    @app.post("/api/item/<item_id>/duration")
    def api_duration(item_id):
        secs = (request.get_json(silent=True) or {}).get("duration", 0)
        try:
            secs = float(secs)
        except (TypeError, ValueError):
            return jsonify({"error": "duration must be a number of seconds"}), 400
        return _mutate(lambda: app.config["LIBRARY"].set_duration(item_id, secs))

    @app.post("/api/item/<item_id>/enabled")
    def api_enabled(item_id):
        on = bool((request.get_json(silent=True) or {}).get("enabled", True))
        return _mutate(lambda: app.config["LIBRARY"].set_enabled(item_id, on))

    @app.post("/api/item/<item_id>/title")
    def api_title(item_id):
        title = str((request.get_json(silent=True) or {}).get("title", ""))
        return _mutate(lambda: app.config["LIBRARY"].set_title(item_id, title))

    @app.post("/api/item/<item_id>/move")
    def api_move(item_id):
        delta = int((request.get_json(silent=True) or {}).get("delta", 0))
        try:
            app.config["LIBRARY"].move(item_id, delta)
        except LibraryError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True})

    @app.post("/api/reorder")
    def api_reorder():
        ids = (request.get_json(silent=True) or {}).get("order", [])
        try:
            app.config["LIBRARY"].reorder(ids)
        except LibraryError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True})

    @app.delete("/api/item/<item_id>")
    def api_delete(item_id):
        try:
            app.config["LIBRARY"].remove(item_id)
        except LibraryError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify({"ok": True})

    @app.post("/api/reload")
    def api_reload():
        # The driver watches library.json's mtime, so touching it is the whole
        # reload protocol.  No socket, nothing to get out of sync.
        lib: Library = app.config["LIBRARY"]
        lib.state_path.touch()
        return jsonify({"ok": True, "version": lib.version})

    # ---- preview -------------------------------------------------------

    def render_png(frame: np.ndarray, scale: int, raw: bool) -> bytes:
        from PIL import Image
        shown = frame if raw else pipeline.to_wire8(frame)
        img = Image.fromarray(shown, "RGB")
        scale = max(1, min(12, scale))
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()

    @app.get("/preview/<item_id>.png")
    def preview_png(item_id):
        lib: Library = app.config["LIBRARY"]
        item = lib.items.get(item_id)
        if item is None:
            abort(404)
        try:
            seq = lib.cache.open_frames(item.id, item.fit)
        except MediaError:
            abort(404)
        n = request.args.get("frame", type=int) or 0
        scale = request.args.get("scale", type=int) or 3
        raw = request.args.get("raw") == "1"
        body = render_png(seq[n], scale, raw)
        return Response(body, mimetype="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/preview/<item_id>.gif")
    def preview_gif(item_id):
        """Animated preview: exactly the frames the wall will show, at wall fps."""
        lib: Library = app.config["LIBRARY"]
        item = lib.items.get(item_id)
        if item is None:
            abort(404)
        try:
            seq = lib.cache.open_frames(item.id, item.fit)
        except MediaError:
            abort(404)
        from PIL import Image

        scale = request.args.get("scale", type=int) or 3
        limit = min(len(seq), request.args.get("frames", type=int) or 150)
        step = max(1, len(seq) // limit)
        raw = request.args.get("raw") == "1"
        frames = []
        for i in range(0, len(seq), step):
            arr = seq[i] if raw else pipeline.to_wire8(seq[i])
            img = Image.fromarray(arr, "RGB").resize(
                (wall.width * scale, wall.height * scale), Image.NEAREST
            )
            frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=256))
            if len(frames) >= limit:
                break
        out = io.BytesIO()
        delay = max(20, int(1000 * step / wall.render.fps))
        frames[0].save(out, "GIF", save_all=True, append_images=frames[1:],
                       duration=delay, loop=0, optimize=False)
        return Response(out.getvalue(), mimetype="image/gif",
                        headers={"Cache-Control": "no-store"})

    @app.get("/now.png")
    def now_png():
        """What the wall is showing at this instant, from the same clock."""
        lib: Library = app.config["LIBRARY"]
        tl = lib.build_timeline()
        scale = request.args.get("scale", type=int) or 3
        index = int((time.time() - wall.render.epoch) * wall.render.fps)
        frame = np.zeros((wall.height, wall.width, 3), np.uint8)
        found = tl.locate(index) if tl.total_frames else None
        if found:
            slot, local = found
            try:
                frame = lib.cache.open_frames(slot.item.id, slot.item.fit)[local]
            except MediaError:
                pass
        return Response(render_png(frame, scale, False), mimetype="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/original/<item_id>")
    def api_original(item_id):
        lib: Library = app.config["LIBRARY"]
        item = lib.items.get(item_id)
        if item is None:
            abort(404)
        return send_file(lib.media_dir / item.stored_name,
                         download_name=item.filename)

    # ---- controllers ---------------------------------------------------

    @app.get("/api/controllers")
    def api_controllers():
        return jsonify({
            "controllers": driver_status().get("controllers", []),
            "expected": [
                {"column": c.column, "ip": c.ip, "ddp_id": c.ddp_id,
                 "pixels": c.n_pixels}
                for c in wall.controllers
            ],
            "table": control.table.map,
        })

    @app.post("/api/controllers/<mac>/assign")
    def api_assign(mac):
        body = request.get_json(silent=True) or {}
        col = body.get("column")
        if col is None:
            control.unassign(mac)
            return jsonify({"ok": True})
        try:
            col = int(col)
            wall.controller_by_column(col)
        except (ValueError, KeyError):
            return jsonify({"error": f"no column {col} in this wall"}), 400
        ok = control.assign(mac, col)
        return jsonify({"ok": ok})

    @app.post("/api/controllers/<mac>/identify")
    def api_identify(mac):
        return jsonify({"ok": control.identify(mac)})

    @app.post("/api/controllers/<mac>/reboot")
    def api_reboot(mac):
        return jsonify({"ok": control.reboot(mac)})

    @app.errorhandler(413)
    def too_big(_e):
        return jsonify({"error": f"file is over the {MAX_UPLOAD_MB} MB limit"}), 413

    return app


def serve(app: Flask, host: str = "0.0.0.0", port: int = 8080) -> None:
    from waitress import serve as waitress_serve
    log.info("upload utility on http://%s:%d", host, port)
    waitress_serve(app, host=host, port=port, threads=8,
                   max_request_body_size=MAX_UPLOAD_MB * 1024 * 1024)
