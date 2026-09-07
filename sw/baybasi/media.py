"""Decoding: media file in, a deterministic 64x192 RGB frame sequence out.

Everything goes through ffmpeg, including stills.  That is deliberate.  The
upload utility has to show the operator exactly what the wall will show, and
the only way to guarantee that is for the preview and the driver to run the
same decoder with the same filter chain and produce the same bytes.

A decoded item is cached as raw ``rgb24`` at wall resolution.  36 864 bytes a
frame is small, memory-maps for free, and makes the driver's inner loop a
slice rather than a decode - which is what lets a Pi 3 hold 30 fps.  It also
makes the two displays bit-identical: identical source file plus identical fit
policy gives an identical cache, and the checksum in the upload utility proves
it.

Still images cache exactly one frame; how long they are held is a property of
the playlist, not of the cache.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

import numpy as np

FIT_POLICIES = ("letterbox", "crop", "stretch")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ANIM_EXT = {".gif", ".webp", ".apng"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mpg", ".mpeg"}
ALLOWED_EXT = IMAGE_EXT | ANIM_EXT | VIDEO_EXT

# swscale kernel.  `area` is box averaging: the right answer when the target is
# 64 px wide and the source is a 4000 px photo, and far kinder than lanczos,
# whose ringing shows up as a bright fringe on a wall this coarse.
SCALE_FLAGS = "area"


class MediaError(RuntimeError):
    pass


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MediaError(
            f"{name} not found on PATH. Install it: sudo apt install ffmpeg"
        )
    return path


def ffmpeg() -> str:
    return _tool("ffmpeg")


def ffprobe() -> str:
    return _tool("ffprobe")


# --------------------------------------------------------------------------
# probing


@dataclass
class Probe:
    ok: bool
    kind: str                # image | animation | video
    width: int = 0
    height: int = 0
    duration: float = 0.0
    n_frames: int = 0
    fps: float = 0.0
    codec: str = ""
    format: str = ""
    error: str = ""

    @property
    def animated(self) -> bool:
        return self.kind != "image"


def probe(path: Path) -> Probe:
    """Validate at upload, so nothing fails at playback in front of people."""
    path = Path(path)
    if not path.exists():
        return Probe(ok=False, kind="", error="file does not exist")
    if path.stat().st_size == 0:
        return Probe(ok=False, kind="", error="file is empty")
    cmd = [
        ffprobe(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return Probe(ok=False, kind="", error="ffprobe timed out")
    if res.returncode != 0:
        msg = res.stderr.decode("utf-8", "replace").strip().splitlines()
        return Probe(ok=False, kind="", error=msg[-1] if msg else "ffprobe failed")

    doc = json.loads(res.stdout or b"{}")
    streams = [s for s in doc.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        return Probe(ok=False, kind="", error="no video or image stream in this file")
    s = streams[0]
    fmt = (doc.get("format") or {}).get("format_name", "")
    codec = s.get("codec_name", "")

    duration = 0.0
    for src in (s.get("duration"), (doc.get("format") or {}).get("duration")):
        try:
            duration = float(src)
            break
        except (TypeError, ValueError):
            continue

    n_frames = 0
    try:
        n_frames = int(s.get("nb_frames") or 0)
    except (TypeError, ValueError):
        n_frames = 0

    fps = 0.0
    rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/0"
    try:
        num, _, den = rate.partition("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    still_codecs = {"mjpeg", "png", "bmp", "webp"}
    if codec in still_codecs and n_frames <= 1 and duration <= 0.06:
        kind = "image"
    elif codec == "gif" or fmt == "gif":
        kind = "animation" if (n_frames > 1 or duration > 0.06) else "image"
    elif n_frames == 1 and duration <= 0.06:
        kind = "image"
    else:
        kind = "video"

    return Probe(
        ok=True, kind=kind,
        width=int(s.get("width") or 0), height=int(s.get("height") or 0),
        duration=duration, n_frames=n_frames, fps=fps, codec=codec, format=fmt,
    )


# --------------------------------------------------------------------------
# the filter chain - the single source of truth for "what the wall will show"


def filter_chain(width: int, height: int, fit: str, *, fps: Optional[float] = None,
                 background: str = "black") -> str:
    if fit not in FIT_POLICIES:
        raise MediaError(f"fit must be one of {FIT_POLICIES}, got {fit!r}")
    parts = []
    if fps:
        parts.append(f"fps={fps}")
    if fit == "stretch":
        parts.append(f"scale={width}:{height}:flags={SCALE_FLAGS}")
    elif fit == "letterbox":
        parts.append(
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
            f"flags={SCALE_FLAGS}"
        )
        parts.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{background}")
    else:  # crop
        parts.append(
            f"scale={width}:{height}:force_original_aspect_ratio=increase:"
            f"flags={SCALE_FLAGS}"
        )
        parts.append(f"crop={width}:{height}")
    parts.append("setsar=1")
    parts.append("format=rgb24")
    return ",".join(parts)


def decode_frames(path: Path, width: int, height: int, fit: str, *,
                  fps: Optional[float] = None, max_frames: Optional[int] = None,
                  timeout: int = 900) -> Iterator[np.ndarray]:
    """Stream ``(height, width, 3) uint8`` frames straight out of ffmpeg."""
    frame_bytes = width * height * 3
    cmd = [
        ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(path),
        "-map", "0:v:0",
        "-vf", filter_chain(width, height, fit, fps=fps),
        "-f", "rawvideo", "-pix_fmt", "rgb24",
    ]
    if max_frames:
        cmd += ["-frames:v", str(max_frames)]
    cmd.append("-")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + timeout
    try:
        while True:
            chunk = proc.stdout.read(frame_bytes)
            if not chunk:
                break
            if len(chunk) < frame_bytes:  # ragged tail, ffmpeg was killed
                break
            yield np.frombuffer(chunk, np.uint8).reshape(height, width, 3)
            if time.monotonic() > deadline:
                raise MediaError(f"decoding {path.name} exceeded {timeout}s")
    finally:
        if proc.stdout:
            proc.stdout.close()
        err = b""
        if proc.poll() is None:
            proc.terminate()
            try:
                _, err = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        else:
            err = proc.stderr.read() if proc.stderr else b""
        if proc.stderr:
            proc.stderr.close()
        if proc.returncode not in (0, None) and not max_frames:
            msg = err.decode("utf-8", "replace").strip().splitlines()
            if msg:
                raise MediaError(f"ffmpeg failed on {path.name}: {msg[-1]}")


# --------------------------------------------------------------------------
# cache


@dataclass
class CacheEntry:
    sha256: str
    fit: str
    width: int
    height: int
    fps: int
    n_frames: int
    kind: str
    source_name: str
    built_at: float
    raw_sha256: str = ""

    @property
    def frame_bytes(self) -> int:
        return self.width * self.height * 3

    @property
    def animated(self) -> bool:
        return self.n_frames > 1


def cache_key(sha: str, fit: str, width: int, height: int, fps: int) -> str:
    return f"{sha}_{fit}_{width}x{height}_{fps}"


class FrameCache:
    """Decoded frame sequences on disk, keyed by content hash and fit policy."""

    def __init__(self, root: Path, width: int, height: int, fps: int):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.width, self.height, self.fps = width, height, fps

    def paths(self, sha: str, fit: str) -> tuple[Path, Path]:
        key = cache_key(sha, fit, self.width, self.height, self.fps)
        return self.root / f"{key}.raw", self.root / f"{key}.json"

    def get(self, sha: str, fit: str) -> Optional[CacheEntry]:
        raw, meta = self.paths(sha, fit)
        if not (raw.exists() and meta.exists()):
            return None
        try:
            entry = CacheEntry(**json.loads(meta.read_text()))
        except (json.JSONDecodeError, TypeError):
            return None
        if raw.stat().st_size != entry.n_frames * entry.frame_bytes:
            return None
        return entry

    def build(self, source: Path, sha: str, fit: str, *, kind: str,
              progress=None) -> CacheEntry:
        raw_path, meta_path = self.paths(sha, fit)
        tmp = raw_path.with_suffix(".raw.part")
        n = 0
        digest = hashlib.sha256()
        still = kind == "image"
        with open(tmp, "wb") as fh:
            for frame in decode_frames(
                source, self.width, self.height, fit,
                fps=None if still else self.fps,
                max_frames=1 if still else None,
            ):
                buf = frame.tobytes()
                fh.write(buf)
                digest.update(buf)
                n += 1
                if progress and n % 30 == 0:
                    progress(n)
        if n == 0:
            tmp.unlink(missing_ok=True)
            raise MediaError(f"{source.name}: ffmpeg produced no frames")
        tmp.replace(raw_path)
        entry = CacheEntry(
            sha256=sha, fit=fit, width=self.width, height=self.height,
            fps=self.fps, n_frames=n, kind=kind, source_name=source.name,
            built_at=time.time(), raw_sha256=digest.hexdigest(),
        )
        meta_path.write_text(json.dumps(asdict(entry), indent=1))
        return entry

    def ensure(self, source: Path, sha: str, fit: str, *, kind: str,
               progress=None) -> CacheEntry:
        return self.get(sha, fit) or self.build(
            source, sha, fit, kind=kind, progress=progress
        )

    def open_frames(self, sha: str, fit: str) -> "FrameSequence":
        entry = self.get(sha, fit)
        if entry is None:
            raise MediaError(f"no cache for {sha[:8]} / {fit}")
        raw, _ = self.paths(sha, fit)
        return FrameSequence(raw, entry)

    def drop(self, sha: str, fit: Optional[str] = None) -> int:
        removed = 0
        fits = [fit] if fit else list(FIT_POLICIES)
        for f in fits:
            for p in self.paths(sha, f):
                if p.exists():
                    p.unlink()
                    removed += 1
        return removed

    def prune(self, keep: Sequence[tuple[str, str]]) -> int:
        """Delete caches for media that is no longer in the library."""
        wanted = {
            cache_key(sha, fit, self.width, self.height, self.fps)
            for sha, fit in keep
        }
        removed = 0
        for p in self.root.iterdir():
            if p.suffix not in (".raw", ".json", ".part"):
                continue
            if p.name.rsplit(".", 1)[0] not in wanted:
                p.unlink()
                removed += 1
        return removed


class FrameSequence:
    """Random access into a cached raw frame file, memory-mapped."""

    def __init__(self, path: Path, entry: CacheEntry):
        self.path, self.entry = Path(path), entry
        self._map = np.memmap(
            self.path, dtype=np.uint8, mode="r",
            shape=(entry.n_frames, entry.height, entry.width, 3),
        )

    def __len__(self) -> int:
        return self.entry.n_frames

    def __getitem__(self, i: int) -> np.ndarray:
        return np.asarray(self._map[i % self.entry.n_frames])

    def close(self) -> None:
        self._map = None


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
