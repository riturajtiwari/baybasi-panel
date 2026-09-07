"""The media library and playlist, and the manifest that keeps two walls equal.

The two displays never talk to each other.  They stay in step because both Pis
derive the frame index from wall-clock time against a shared epoch, which only
works if both are playing *the same timeline*.  So the playlist compiles to a
deterministic timeline - an ordered list of (media, fit, frame count) with a
total frame count - and the manifest digest over that timeline is what an
operator compares between the two Pis.

If the digests match, the walls match.  If they differ, the utility says which
item differs and in what way.  That is the whole synchronisation contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .media import (
    ALLOWED_EXT, FIT_POLICIES, CacheEntry, FrameCache, MediaError, Probe,
    probe, sha256_file,
)

DEFAULT_STILL_SECONDS = 8.0


class LibraryError(RuntimeError):
    pass


@dataclass
class Item:
    id: str                      # sha256 of the original file
    filename: str                # original name, for humans
    ext: str
    size: int
    kind: str                    # image | animation | video
    src_width: int = 0
    src_height: int = 0
    src_duration: float = 0.0
    fit: str = "letterbox"
    duration: float = 0.0        # seconds; 0 = natural length (animated only)
    enabled: bool = True
    added_at: float = field(default_factory=time.time)
    title: str = ""
    note: str = ""

    @property
    def display_title(self) -> str:
        return self.title or self.filename

    @property
    def stored_name(self) -> str:
        return f"{self.id}{self.ext}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TimelineSlot:
    item: Item
    cache: CacheEntry
    start: int                   # first global frame index
    frames: int                  # how many global frames this slot occupies

    @property
    def end(self) -> int:
        return self.start + self.frames


@dataclass
class Timeline:
    slots: List[TimelineSlot]
    fps: int
    total_frames: int
    digest: str

    def locate(self, global_index: int) -> Optional[Tuple[TimelineSlot, int]]:
        """Global frame index -> (slot, frame within that slot's cache)."""
        if not self.slots or self.total_frames <= 0:
            return None
        g = global_index % self.total_frames
        lo, hi = 0, len(self.slots) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            s = self.slots[mid]
            if g < s.start:
                hi = mid - 1
            elif g >= s.end:
                lo = mid + 1
            else:
                return s, (g - s.start) % s.cache.n_frames
        return None

    def describe(self) -> str:
        secs = self.total_frames / self.fps if self.fps else 0
        lines = [
            f"timeline {len(self.slots)} item(s), {self.total_frames} frames, "
            f"{secs:.1f}s, digest {self.digest[:12]}"
        ]
        for s in self.slots:
            lines.append(
                f"  [{s.start:6d}..{s.end - 1:6d}] {s.frames:6d}f "
                f"{s.item.fit:9s} {s.item.display_title}"
            )
        return "\n".join(lines)


class Library:
    """Media store, playlist and cache, on disk under one root."""

    STATE = "library.json"

    def __init__(self, root: Path, width: int, height: int, fps: int):
        self.root = Path(root)
        self.media_dir = self.root / "media"
        self.cache_dir = self.root / "cache"
        self.root.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        self.width, self.height, self.fps = width, height, fps
        self.cache = FrameCache(self.cache_dir, width, height, fps)
        self.items: Dict[str, Item] = {}
        self.order: List[str] = []
        self.version = 0
        self._lock = threading.RLock()
        self.load()

    # ---- persistence ---------------------------------------------------

    @property
    def state_path(self) -> Path:
        return self.root / self.STATE

    def load(self) -> None:
        with self._lock:
            if not self.state_path.exists():
                self.items, self.order, self.version = {}, [], 0
                return
            try:
                doc = json.loads(self.state_path.read_text())
            except json.JSONDecodeError as exc:
                raise LibraryError(f"{self.state_path} is corrupt: {exc}") from exc
            self.items = {}
            for d in doc.get("items", []):
                known = {f for f in Item.__dataclass_fields__}
                self.items[d["id"]] = Item(**{k: v for k, v in d.items() if k in known})
            self.order = [i for i in doc.get("order", []) if i in self.items]
            for i in self.items:
                if i not in self.order:
                    self.order.append(i)
            self.version = int(doc.get("version", 0))

    def save(self) -> None:
        with self._lock:
            self.version += 1
            doc = {
                "version": self.version,
                "saved_at": time.time(),
                "wall": {"width": self.width, "height": self.height, "fps": self.fps},
                "order": self.order,
                "items": [self.items[i].to_dict() for i in self.order],
            }
            _atomic_write(self.state_path, json.dumps(doc, indent=1).encode())

    def mtime(self) -> float:
        try:
            return self.state_path.stat().st_mtime
        except OSError:
            return 0.0

    # ---- mutation ------------------------------------------------------

    def add_file(self, src: Path, *, filename: Optional[str] = None,
                 fit: str = "letterbox", duration: Optional[float] = None,
                 progress=None) -> Item:
        """Validate, store by content hash, decode into the cache, add to the end."""
        src = Path(src)
        name = filename or src.name
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXT:
            raise LibraryError(
                f"{name}: {ext or 'no extension'} is not supported. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXT))}"
            )
        if fit not in FIT_POLICIES:
            raise LibraryError(f"fit must be one of {FIT_POLICIES}, got {fit!r}")

        info = probe(src)
        if not info.ok:
            raise LibraryError(f"{name}: {info.error}")

        sha = sha256_file(src)
        stored = self.media_dir / f"{sha}{ext}"
        newly_stored = not stored.exists()
        if newly_stored:
            _copy(src, stored)

        with self._lock:
            existing = self.items.get(sha)
            if existing is not None:
                # Same bytes already in the library.  Re-adding is a no-op except
                # for an explicit fit change, which is what the operator meant.
                if existing.fit != fit:
                    self.set_fit(sha, fit)
                return existing

            if duration is None:
                duration = DEFAULT_STILL_SECONDS if info.kind == "image" else 0.0

            item = Item(
                id=sha, filename=name, ext=ext, size=stored.stat().st_size,
                kind=info.kind, src_width=info.width, src_height=info.height,
                src_duration=info.duration, fit=fit, duration=float(duration),
            )
            # Decode before the item exists.  A file that ffprobe accepts can
            # still produce no frames; the library must not end up holding an
            # entry that the driver cannot play, nor an orphaned upload.
            try:
                self.cache.ensure(stored, sha, fit, kind=info.kind,
                                  progress=progress)
            except MediaError as exc:
                self.cache.drop(sha)
                if newly_stored:
                    stored.unlink(missing_ok=True)
                raise LibraryError(f"{name}: {exc}") from exc

            self.items[sha] = item
            self.order.append(sha)
            self.save()
            return item

    def remove(self, item_id: str) -> None:
        with self._lock:
            item = self.items.pop(item_id, None)
            if item is None:
                raise LibraryError(f"no such item {item_id[:8]}")
            self.order = [i for i in self.order if i != item_id]
            self.cache.drop(item_id)
            stored = self.media_dir / item.stored_name
            if stored.exists():
                stored.unlink()
            self.save()

    def set_fit(self, item_id: str, fit: str, progress=None) -> Item:
        if fit not in FIT_POLICIES:
            raise LibraryError(f"fit must be one of {FIT_POLICIES}, got {fit!r}")
        with self._lock:
            item = self._get(item_id)
            if item.fit != fit:
                # Build the new cache before dropping the old one, so a failed
                # decode leaves the item playable instead of leaving a hole.
                self.cache.ensure(
                    self.media_dir / item.stored_name, item.id, fit,
                    kind=item.kind, progress=progress,
                )
                previous, item.fit = item.fit, fit
                self.cache.drop(item.id, previous)
                self.save()
            return item

    def set_duration(self, item_id: str, seconds: float) -> Item:
        with self._lock:
            item = self._get(item_id)
            item.duration = max(0.0, float(seconds))
            self.save()
            return item

    def set_enabled(self, item_id: str, enabled: bool) -> Item:
        with self._lock:
            item = self._get(item_id)
            item.enabled = bool(enabled)
            self.save()
            return item

    def set_title(self, item_id: str, title: str) -> Item:
        with self._lock:
            item = self._get(item_id)
            item.title = title.strip()[:120]
            self.save()
            return item

    def reorder(self, ids: Sequence[str]) -> None:
        with self._lock:
            known = set(self.items)
            new = [i for i in ids if i in known]
            if set(new) != known:
                missing = known - set(new)
                raise LibraryError(
                    f"reorder must list every item; missing {len(missing)}"
                )
            self.order = list(new)
            self.save()

    def move(self, item_id: str, delta: int) -> None:
        with self._lock:
            self._get(item_id)
            i = self.order.index(item_id)
            j = max(0, min(len(self.order) - 1, i + delta))
            if i != j:
                self.order.insert(j, self.order.pop(i))
                self.save()

    def _get(self, item_id: str) -> Item:
        item = self.items.get(item_id)
        if item is None:
            raise LibraryError(f"no such item {item_id[:8]}")
        return item

    # ---- reading -------------------------------------------------------

    def ordered(self) -> List[Item]:
        return [self.items[i] for i in self.order if i in self.items]

    def enabled(self) -> List[Item]:
        return [i for i in self.ordered() if i.enabled]

    def slot_frames(self, item: Item, cache: CacheEntry) -> int:
        if item.duration and item.duration > 0:
            return max(1, int(round(item.duration * self.fps)))
        if cache.n_frames <= 1:
            return max(1, int(round(DEFAULT_STILL_SECONDS * self.fps)))
        return cache.n_frames

    def build_timeline(self) -> Timeline:
        """Compile the playlist into the deterministic global frame timeline."""
        with self._lock:
            slots: List[TimelineSlot] = []
            cursor = 0
            parts: List[str] = []
            for item in self.enabled():
                entry = self.cache.get(item.id, item.fit)
                if entry is None:
                    stored = self.media_dir / item.stored_name
                    if not stored.exists():
                        continue
                    entry = self.cache.ensure(
                        stored, item.id, item.fit, kind=item.kind
                    )
                frames = self.slot_frames(item, entry)
                slots.append(TimelineSlot(item=item, cache=entry,
                                          start=cursor, frames=frames))
                cursor += frames
                # The digest covers exactly what makes two walls show the same
                # thing: which pixels, in what order, for how long.
                parts.append(
                    f"{item.id}:{entry.raw_sha256}:{item.fit}:{frames}"
                )
            digest = hashlib.sha256(
                ("|".join(parts) + f"#fps={self.fps}"
                 f"#size={self.width}x{self.height}").encode()
            ).hexdigest()
            return Timeline(slots=slots, fps=self.fps,
                            total_frames=cursor, digest=digest)

    def manifest(self) -> dict:
        """What the operator compares between the two Pis."""
        tl = self.build_timeline()
        return {
            "digest": tl.digest,
            "fps": self.fps,
            "size": f"{self.width}x{self.height}",
            "total_frames": tl.total_frames,
            "duration_s": round(tl.total_frames / self.fps, 3) if self.fps else 0,
            "count": len(tl.slots),
            "items": [
                {
                    "n": n,
                    "id": s.item.id,
                    "short": s.item.id[:12],
                    "title": s.item.display_title,
                    "filename": s.item.filename,
                    "kind": s.item.kind,
                    "fit": s.item.fit,
                    "frames": s.frames,
                    "seconds": round(s.frames / self.fps, 3) if self.fps else 0,
                    "pixels_sha256": s.cache.raw_sha256[:16],
                }
                for n, s in enumerate(tl.slots)
            ],
        }

    def prune_cache(self) -> int:
        with self._lock:
            keep = [(i.id, i.fit) for i in self.items.values()]
            return self.cache.prune(keep)


def compare_manifests(a: dict, b: dict) -> List[str]:
    """Explain a mismatch between two Pis in terms an operator can act on."""
    out: List[str] = []
    if a.get("digest") == b.get("digest"):
        return []
    if a.get("fps") != b.get("fps"):
        out.append(f"fps differs: {a.get('fps')} vs {b.get('fps')}")
    if a.get("size") != b.get("size"):
        out.append(f"wall size differs: {a.get('size')} vs {b.get('size')}")

    ia = {i["id"]: i for i in a.get("items", [])}
    ib = {i["id"]: i for i in b.get("items", [])}
    for missing in [i for i in ia if i not in ib]:
        out.append(f"only on A: {ia[missing]['title']} ({missing[:8]})")
    for missing in [i for i in ib if i not in ia]:
        out.append(f"only on B: {ib[missing]['title']} ({missing[:8]})")
    for k in ia.keys() & ib.keys():
        x, y = ia[k], ib[k]
        if x["fit"] != y["fit"]:
            out.append(f"{x['title']}: fit {x['fit']} vs {y['fit']}")
        elif x["frames"] != y["frames"]:
            out.append(f"{x['title']}: {x['frames']} frames vs {y['frames']}")
        elif x["pixels_sha256"] != y["pixels_sha256"]:
            out.append(f"{x['title']}: decoded pixels differ (different ffmpeg?)")
    order_a = [i["id"] for i in a.get("items", [])]
    order_b = [i["id"] for i in b.get("items", [])]
    if set(order_a) == set(order_b) and order_a != order_b:
        out.append("same media, different playlist order")
    if not out:
        out.append("digests differ but no field-level difference was found")
    return out


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _copy(src: Path, dst: Path) -> None:
    import shutil
    tmp = dst.with_suffix(dst.suffix + ".part")
    shutil.copyfile(src, tmp)
    tmp.replace(dst)
