"""Read-only system status: battery, disk, Wi-Fi network, load. Best-effort and cross-platform."""

import os
import platform
import re
import shutil
import subprocess
import sys

from core.action_result import ActionResult
from remote_tools.registry import register, ToolContext, RISK_READ


def _run(cmd: list, timeout: float = 4.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _battery() -> dict:
    if sys.platform == "darwin":
        out = _run(["pmset", "-g", "batt"])
        m = re.search(r"(\d+)%", out)
        if m:
            return {"percent": int(m.group(1)),
                    "charging": "charging" in out and "discharging" not in out,
                    "on_ac": "AC Power" in out}
    elif sys.platform.startswith("linux"):
        base = "/sys/class/power_supply"
        try:
            for name in sorted(os.listdir(base)):
                if name.startswith("BAT"):
                    with open(os.path.join(base, name, "capacity")) as f:
                        pct = int(f.read().strip())
                    with open(os.path.join(base, name, "status")) as f:
                        status = f.read().strip().lower()
                    return {"percent": pct, "charging": status == "charging", "on_ac": status != "discharging"}
        except Exception:
            pass
    return {}


def _wifi() -> dict:
    if sys.platform == "darwin":
        out = _run(["networksetup", "-getairportnetwork", "en0"])
        m = re.search(r"Current Wi-Fi Network:\s*(.+)", out)
        if m:
            return {"connected": True, "network": m.group(1).strip()}
        if out:
            return {"connected": False}
    return {}


@register(
    "system_status",
    description="Report the laptop's current status: battery, disk space, Wi-Fi network, load and OS.",
    label="Check system status",
    parameters={"type": "object", "properties": {}},
    risk=RISK_READ,
)
def system_status(args: dict, ctx: ToolContext) -> ActionResult:
    data = {"os": f"{platform.system()} {platform.release()}", "host": platform.node()}
    try:
        du = shutil.disk_usage(os.path.expanduser("~"))
        data["disk"] = {"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1)}
    except Exception:
        pass
    try:
        data["load_avg"] = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        pass
    for key, fn in (("battery", _battery), ("wifi", _wifi)):
        info = fn()
        if info:
            data[key] = info
    parts = []
    if "battery" in data:
        parts.append(f"battery {data['battery']['percent']}%")
    if "disk" in data:
        parts.append(f"{data['disk']['free_gb']} GB free")
    if data.get("wifi", {}).get("network"):
        parts.append(f"Wi-Fi {data['wifi']['network']}")
    return ActionResult.ok("system_status", ", ".join(parts) or "Status collected", data=data)
