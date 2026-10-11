"""Local resource checks used before dispatching an image render."""
from __future__ import annotations

import platform
import re
import subprocess
from collections import defaultdict
from pathlib import Path

GIB = 1024 ** 3
RECOMMENDED_IMAGE_MEMORY_GB = 14.0


def _run(command: list[str]) -> str:
    return subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=10
    ).stdout


def _mac_available_bytes(vm_stat: str) -> int:
    page_match = re.search(r"page size of (\d+) bytes", vm_stat)
    if not page_match:
        raise RuntimeError("vm_stat did not report its page size")
    page_size = int(page_match.group(1))
    pages: dict[str, int] = {}
    for line in vm_stat.splitlines():
        match = re.match(r"([^:]+):\s+(\d+)\.?$", line.strip())
        if match:
            pages[match.group(1)] = int(match.group(2))
    # This matches the useful-memory definition used by common macOS system
    # monitors: immediately free pages plus reclaimable inactive/speculative
    # pages. Purgeable pages are already represented in those VM buckets.
    available_pages = sum(
        pages.get(name, 0)
        for name in ("Pages free", "Pages inactive", "Pages speculative")
    )
    return available_pages * page_size


def _linux_available_bytes(meminfo: str) -> int:
    match = re.search(r"^MemAvailable:\s+(\d+)\s+kB$", meminfo, re.MULTILINE)
    if not match:
        raise RuntimeError("/proc/meminfo did not report MemAvailable")
    return int(match.group(1)) * 1024


def available_memory_bytes() -> int:
    system = platform.system()
    if system == "Darwin":
        return _mac_available_bytes(_run(["vm_stat"]))
    if system == "Linux":
        return _linux_available_bytes(Path("/proc/meminfo").read_text())

    page_size = int(_run(["getconf", "PAGE_SIZE"]).strip())
    available_pages = int(_run(["getconf", "_AVPHYS_PAGES"]).strip())
    return page_size * available_pages


def _application_name(command: str) -> str:
    lower = command.lower()
    known = (
        ("google chrome", "Google Chrome"),
        ("visual studio code", "Visual Studio Code"),
        ("code helper", "Visual Studio Code"),
        ("com.docker", "Docker"),
        ("docker desktop", "Docker"),
        ("virtualization.virtualmachine", "Docker"),
        ("ollama", "Ollama"),
        ("comfyui", "ComfyUI"),
        ("safari", "Safari"),
        ("slack", "Slack"),
    )
    for needle, name in known:
        if needle in lower:
            return name

    app_match = re.search(r"/([^/]+)\.app/Contents/", command, re.IGNORECASE)
    if app_match:
        return app_match.group(1)
    executable = command.strip().split(maxsplit=1)[0] if command.strip() else "Unknown"
    return Path(executable).name or "Unknown"


def top_memory_consumers(limit: int = 3) -> list[dict]:
    totals_kib: dict[str, int] = defaultdict(int)
    try:
        output = _run(["ps", "-axo", "rss=,command="])
    except (OSError, subprocess.SubprocessError):
        # Sandboxed/containerized deployments may expose memory totals while
        # denying process-list access. The readiness decision remains valid;
        # the UI simply has no app suggestions to show in that environment.
        return []
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\s+(.+)$", line)
        if not match:
            continue
        totals_kib[_application_name(match.group(2))] += int(match.group(1))

    ranked = sorted(totals_kib.items(), key=lambda item: item[1], reverse=True)
    return [
        {"name": name, "memory_gb": round(kib * 1024 / GIB, 2)}
        for name, kib in ranked[:limit]
    ]


def image_readiness() -> dict:
    available = available_memory_bytes()
    recommended = int(RECOMMENDED_IMAGE_MEMORY_GB * GIB)
    return {
        "available_bytes": available,
        "available_gb": round(available / GIB, 2),
        "recommended_gb": RECOMMENDED_IMAGE_MEMORY_GB,
        "enough_memory": available >= recommended,
        "top_consumers": top_memory_consumers(),
    }
