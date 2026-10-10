# Stamp the firmware with the git revision it was built from.
#
# Every board announces FW_VERSION = FW_SEMVER "+" FW_GIT, so `baybasi
# discover` names the exact build running on each column. A "-dirty" suffix
# means the image came from uncommitted source.
Import("env")  # noqa: F821 - SCons provides it
import subprocess


def _rev():
    try:
        out = subprocess.check_output(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            cwd=env.subst("$PROJECT_DIR"),  # noqa: F821
            stderr=subprocess.DEVNULL, text=True).strip()
        return out or "nogit"
    except Exception:
        return "nogit"


env.Append(CPPDEFINES=[("FW_GIT", env.StringifyMacro(_rev()))])  # noqa: F821
print("baybasi fw git revision:", _rev())
