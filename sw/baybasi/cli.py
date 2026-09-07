"""``baybasi`` - one entry point for the sink, the driver and the utility."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG = "config/wall.yaml"
DEFAULT_DATA = "data"


def _log(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _wall(args):
    from .geometry import Wall
    path = Path(args.config)
    if not path.exists():
        sys.exit(f"no wall config at {path}. Pass --config, or copy {DEFAULT_CONFIG}.")
    wall = Wall.load(path)
    if getattr(args, "brightness", None) is not None:
        wall.render.brightness = args.brightness
    if getattr(args, "fps", None):
        wall.render.fps = args.fps
    if getattr(args, "target", None):
        # Point every controller and the broadcast at one host: this is how you
        # drive the software sink, or one board on the bench.
        for c in wall.controllers:
            c.ip = args.target
        wall.network.broadcast = args.target
    if getattr(args, "port", None):
        wall.network.ddp_port = args.port
    return wall


def _library(args, wall):
    from .library import Library
    return Library(Path(args.data), wall.width, wall.height, wall.render.fps)


# --------------------------------------------------------------------------
# commands


def cmd_check(args) -> int:
    from .sender import bandwidth_report, check_wire_limits
    wall = _wall(args)
    print(wall.describe())
    print()
    cov = wall.coverage()
    print(f"coverage: {cov['driven']}/{cov['total']} pixels driven, "
          f"{cov['unmapped']} unmapped, {cov['duplicated']} driven twice")
    print(bandwidth_report(wall))
    fps = wall.render.fps
    print(f"frame budget {1000 / fps:.2f} ms; one 256-LED strand needs 7.98 ms "
          f"(125 fps ceiling)")
    problems = list(check_wire_limits(wall))
    if cov["unmapped"]:
        problems.append(f"{cov['unmapped']} wall pixels have no controller")
    if cov["duplicated"]:
        problems.append(f"{cov['duplicated']} wall pixels are driven twice")
    if shutil.which("ffmpeg") is None:
        problems.append("ffmpeg is not on PATH; media cannot be decoded")
    print()
    if problems:
        for p in problems:
            print(f"  PROBLEM  {p}")
        return 1
    print("  no problems found")
    return 0


def cmd_sink(args) -> int:
    from .sink import DDPReceiver, DDPSink, PngWriter, frame_to_ansi
    wall = _wall(args)
    web = None
    on_frame = None
    on_violation = (lambda m: logging.getLogger("sink").warning(m))

    if args.out == "png":
        writer = PngWriter(Path(args.png_dir), scale=args.scale,
                           every=args.every, limit=args.frames,
                           grid=args.grid, wall=wall)
        on_frame = writer
    elif args.out == "ansi":
        def on_frame(frame):
            sys.stdout.write("\x1b[H\x1b[2J" + frame_to_ansi(frame, args.ansi_step) + "\n")
            sys.stdout.flush()

    sink = DDPSink(wall, strict=not args.lax, on_frame=on_frame,
                   on_violation=on_violation)

    if args.out == "web":
        from .sinkweb import SinkWeb
        web = SinkWeb(sink, wall, scale=args.scale, port=args.http_port)
        sink.on_frame = web.on_frame
        sink.on_violation = web.on_violation
        web.start()
        print(f"sink viewer: http://localhost:{args.http_port}")

    receiver = DDPReceiver(sink, host=args.bind, port=wall.network.ddp_port)
    receiver.start()
    print(f"listening for DDP on {args.bind}:{wall.network.ddp_port} "
          f"as {len(wall.controllers)} controller(s)")
    print(wall.describe())
    print()

    try:
        last = time.monotonic()
        while True:
            time.sleep(0.5)
            if args.out == "png" and on_frame.done.is_set():
                break
            if args.out != "ansi" and time.monotonic() - last >= 2.0:
                last = time.monotonic()
                sys.stdout.write("\r" + sink.summary_line().ljust(78))
                sys.stdout.flush()
            if args.seconds and time.monotonic() - sink.stats.started > args.seconds:
                break
    except KeyboardInterrupt:
        pass
    finally:
        receiver.stop()
        sink.flush()
        sink.close()
        if web:
            web.stop()
    print()
    print(json.dumps(sink.status(), indent=1))
    return 0


def cmd_pattern(args) -> int:
    from . import patterns
    from .pixels import Pipeline
    from .sender import DDPSender, WallClockPacer
    wall = _wall(args)
    kw = {}
    if args.pattern == "scroll":
        kw = {"speed": args.speed}
    if args.pattern == "solid":
        kw = {"color": tuple(int(x) for x in args.color.split(","))}
    pat = patterns.build(args.pattern, wall, **kw)
    pipe = Pipeline(wall)
    pacer = WallClockPacer(wall.render.fps, wall.render.epoch)
    print(f"sending '{args.pattern}' to {[c.ip for c in wall.controllers]} "
          f"port {wall.network.ddp_port}, push -> {wall.network.broadcast}")
    n = 0
    with DDPSender(wall, pipeline=pipe) as tx:
        try:
            while args.frames is None or n < args.frames:
                i = pacer.wait()
                tx.send_frame(pat.frame(i))
                n += 1
                if n % wall.render.fps == 0:
                    sys.stdout.write(
                        f"\r{n} frames, {pacer.stats.fps():5.2f} fps, "
                        f"{tx.stats.errors} send errors")
                    sys.stdout.flush()
        except KeyboardInterrupt:
            pass
        finally:
            print()
            tx.blackout()
    return 0


def cmd_driver(args) -> int:
    from .driver import Driver
    wall = _wall(args)
    library = None if args.pattern else _library(args, wall)
    kw = {"speed": args.speed} if args.pattern == "scroll" else {}
    drv = Driver(
        wall, library=library, pattern=args.pattern, pattern_kwargs=kw,
        status_dir=Path(args.data), control=not args.no_control,
    )
    drv.install_signal_handlers()
    drv.run(max_frames=args.frames)
    return 0


def cmd_web(args) -> int:
    from .webapp import create_app, serve
    wall = _wall(args)
    library = _library(args, wall)
    app = create_app(wall, library, status_dir=Path(args.data),
                     table_path=Path(args.data) / "controllers.json")
    serve(app, host=args.bind, port=args.http_port)
    return 0


def cmd_add(args) -> int:
    wall = _wall(args)
    lib = _library(args, wall)
    rc = 0
    for path in args.files:
        p = Path(path)
        try:
            item = lib.add_file(p, fit=args.fit, duration=args.duration)
            print(f"added {item.display_title}  {item.kind}  fit={item.fit}  {item.id[:12]}")
        except Exception as exc:                          # noqa: BLE001
            print(f"FAILED {p.name}: {exc}", file=sys.stderr)
            rc = 1
    print()
    print(lib.build_timeline().describe())
    return rc


def cmd_playlist(args) -> int:
    wall = _wall(args)
    lib = _library(args, wall)
    tl = lib.build_timeline()
    print(tl.describe())
    print()
    print(f"manifest digest: {tl.digest}")
    print("Both Pis must show this same digest.")
    return 0


def cmd_manifest(args) -> int:
    wall = _wall(args)
    lib = _library(args, wall)
    doc = lib.manifest()
    if args.compare:
        from .library import compare_manifests
        other = json.loads(Path(args.compare).read_text())
        diffs = compare_manifests(doc, other)
        if not diffs:
            print("MATCH - both walls will show the same thing")
            return 0
        print("DIFFERS:")
        for d in diffs:
            print(f"  {d}")
        return 1
    print(json.dumps(doc, indent=2))
    return 0


def cmd_discover(args) -> int:
    from .control import ControlPlane
    wall = _wall(args)
    cp = ControlPlane(wall, table_path=Path(args.data) / "controllers.json")
    cp.start()
    print(f"listening for announcements on udp/{wall.network.control_port} "
          f"for {args.seconds}s")
    end = time.monotonic() + args.seconds
    try:
        while time.monotonic() < end:
            time.sleep(1.0)
            sys.stdout.write("\x1b[H\x1b[2J" + cp.firmware_report() + "\n")
    except KeyboardInterrupt:
        pass
    finally:
        cp.stop()
    print(cp.firmware_report())
    return 0


def cmd_assign(args) -> int:
    from .control import ControlPlane
    wall = _wall(args)
    cp = ControlPlane(wall, table_path=Path(args.data) / "controllers.json",
                      listen=False)
    ok = cp.assign(args.mac, args.column)
    print(f"assign {args.mac} -> column {args.column}: {'sent' if ok else 'FAILED'}")
    return 0 if ok else 1


def cmd_ota(args) -> int:
    from .control import ControlPlane, FirmwareServer
    import hashlib
    wall = _wall(args)
    image = Path(args.image)
    if not image.exists():
        sys.exit(f"no firmware image at {image}")
    fw_dir = Path(args.data) / "firmware"
    fw_dir.mkdir(parents=True, exist_ok=True)
    dst = fw_dir / image.name
    if dst.resolve() != image.resolve():
        shutil.copyfile(image, dst)
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()

    server = FirmwareServer(fw_dir, port=args.http_port)
    server.start()
    url = server.url_for(dst.name, args.pi_ip)
    cp = ControlPlane(wall, table_path=Path(args.data) / "controllers.json",
                      listen=False)
    macs = args.mac or list(cp.table.map)
    if not macs:
        sys.exit("no MACs given and the assignment table is empty; "
                 "run `baybasi discover` first")
    for mac in macs:
        print(f"ota {mac} <- {url} ({sha[:12]})")
        cp.ota(mac, url, sha256=sha, version=args.version)
    print(f"serving {dst.name} for {args.hold}s while the boards fetch it")
    time.sleep(args.hold)
    server.stop()
    return 0


def cmd_status(args) -> int:
    from .driver import read_status
    doc = read_status(Path(args.data))
    if doc is None:
        print("driver is not running (no driver-status.json)")
        return 1
    print(json.dumps(doc, indent=1))
    return 0


def cmd_render(args) -> int:
    """Render frames to PNG without any network. The offline sanity check."""
    from PIL import Image
    from . import patterns
    from .pixels import Pipeline
    wall = _wall(args)
    pipe = Pipeline(wall)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.pattern:
        src = patterns.build(args.pattern, wall)
        frames = [src.frame(i) for i in range(args.frames)]
    else:
        lib = _library(args, wall)
        tl = lib.build_timeline()
        frames = []
        for i in range(args.frames):
            found = tl.locate(i)
            if not found:
                break
            slot, local = found
            frames.append(lib.cache.open_frames(slot.item.id, slot.item.fit)[local])
    for i, f in enumerate(frames):
        img = Image.fromarray(pipe.to_wire8(f), "RGB")
        img = img.resize((wall.width * args.scale, wall.height * args.scale),
                         Image.NEAREST)
        img.save(out / f"frame_{i:05d}.png")
    print(f"wrote {len(frames)} PNG(s) to {out}")
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="baybasi",
        description="Baybasi pixel wall: driver, upload utility and DDP test sink.",
    )
    p.add_argument("--config", default=DEFAULT_CONFIG, help="wall geometry YAML")
    p.add_argument("--data", default=DEFAULT_DATA, help="media library directory")
    p.add_argument("--log", default="INFO", help="DEBUG/INFO/WARNING")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="validate the wall config and print the wire budget")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("sink", help="software DDP sink: render what the wall would show")
    s.add_argument("--bind", default="0.0.0.0")
    s.add_argument("--out", choices=("web", "ansi", "png"), default="web")
    s.add_argument("--http-port", type=int, default=8088)
    s.add_argument("--scale", type=int, default=4, help="pixel magnification")
    s.add_argument("--grid", action="store_true", help="overlay panel boundaries")
    s.add_argument("--ansi-step", type=int, default=2, help="ANSI downsample factor")
    s.add_argument("--png-dir", default="sink-frames")
    s.add_argument("--every", type=int, default=1, help="write every Nth frame")
    s.add_argument("--frames", type=int, default=None, help="stop after N frames")
    s.add_argument("--seconds", type=float, default=None)
    s.add_argument("--lax", action="store_true",
                   help="show torn frames instead of dropping them")
    s.add_argument("--port", type=int, default=None)
    s.set_defaults(func=cmd_sink)

    from . import patterns as _pat
    t = sub.add_parser("pattern", help="send a test pattern to the wall or the sink")
    t.add_argument("pattern", choices=_pat.NAMES)
    t.add_argument("--target", help="send everything to this host (the sink)")
    t.add_argument("--port", type=int, default=None)
    t.add_argument("--frames", type=int, default=None)
    t.add_argument("--speed", type=int, default=1)
    t.add_argument("--color", default="255,255,255")
    t.add_argument("--brightness", type=float, default=None)
    t.add_argument("--fps", type=int, default=None)
    t.set_defaults(func=cmd_pattern)

    d = sub.add_parser("driver", help="run the wall")
    d.add_argument("--pattern", choices=_pat.NAMES, default=None,
                   help="play a test pattern instead of the playlist")
    d.add_argument("--target", help="send everything to this host (the sink)")
    d.add_argument("--port", type=int, default=None)
    d.add_argument("--frames", type=int, default=None)
    d.add_argument("--speed", type=int, default=1)
    d.add_argument("--brightness", type=float, default=None)
    d.add_argument("--fps", type=int, default=None)
    d.add_argument("--no-control", action="store_true",
                   help="do not listen for controller announcements")
    d.set_defaults(func=cmd_driver)

    w = sub.add_parser("web", help="run the upload utility")
    w.add_argument("--bind", default="0.0.0.0")
    w.add_argument("--http-port", type=int, default=8080)
    w.set_defaults(func=cmd_web)

    a = sub.add_parser("add", help="add media from the command line")
    a.add_argument("files", nargs="+")
    a.add_argument("--fit", choices=("letterbox", "crop", "stretch"),
                   default="letterbox")
    a.add_argument("--duration", type=float, default=None,
                   help="seconds on screen; 0 = natural length")
    a.set_defaults(func=cmd_add)

    pl = sub.add_parser("playlist", help="show the compiled timeline")
    pl.set_defaults(func=cmd_playlist)

    m = sub.add_parser("manifest", help="print or compare the manifest")
    m.add_argument("--compare", help="path to the other Pi's manifest.json")
    m.set_defaults(func=cmd_manifest)

    disc = sub.add_parser("discover", help="watch for controllers announcing themselves")
    disc.add_argument("--seconds", type=float, default=30)
    disc.set_defaults(func=cmd_discover)

    asg = sub.add_parser("assign", help="give a board its column")
    asg.add_argument("mac")
    asg.add_argument("column", type=int)
    asg.set_defaults(func=cmd_assign)

    o = sub.add_parser("ota", help="push firmware to the boards over Ethernet")
    o.add_argument("image")
    o.add_argument("--mac", action="append", help="repeat; default is every known board")
    o.add_argument("--pi-ip", default="192.168.50.1")
    o.add_argument("--http-port", type=int, default=8080)
    o.add_argument("--version", default="")
    o.add_argument("--hold", type=float, default=60)
    o.set_defaults(func=cmd_ota)

    st = sub.add_parser("status", help="what the running driver reports")
    st.set_defaults(func=cmd_status)

    r = sub.add_parser("render", help="render frames to PNG, no network")
    r.add_argument("--pattern", choices=_pat.NAMES, default=None)
    r.add_argument("--frames", type=int, default=30)
    r.add_argument("--scale", type=int, default=4)
    r.add_argument("--out-dir", default="render")
    r.set_defaults(func=cmd_render)

    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    _log(args.log)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
