# Stamp the firmware with the revision of the FIRMWARE, not of the repo.
#
# Every board announces FW_VERSION = FW_SEMVER "+" FW_GIT, so `baybasi
# discover` names the exact build running on each column.
#
# FW_GIT is the last commit that touched the firmware's own source - src/,
# platformio.ini and this script - with "-dirty" only if one of THOSE has
# uncommitted changes. Stamping the repo's HEAD instead (the first version of
# this script) meant any commit at all - a docs edit, a Pi-side change, a bench
# tool - gave newly flashed boards a new version with byte-for-byte identical
# firmware, so a wall built across an evening showed four "different" builds.
Import("env")  # noqa: F821 - SCons provides it
import subprocess

FW_SOURCE = ["src", "platformio.ini", "git_rev.py"]


def _git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=env.subst("$PROJECT_DIR"),  # noqa: F821
        stderr=subprocess.DEVNULL, text=True).strip()


def _rev():
    try:
        sha = _git("log", "-1", "--format=%h", "--abbrev=7", "--", *FW_SOURCE)
        dirty = _git("status", "--porcelain", "--", *FW_SOURCE)
        return (sha or "nogit") + ("-dirty" if dirty else "")
    except Exception:
        return "nogit"


env.Append(CPPDEFINES=[("FW_GIT", env.StringifyMacro(_rev()))])  # noqa: F821
print("baybasi fw git revision:", _rev())
