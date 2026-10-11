import asyncio

from app.services import resource_service
from app.services.resource_service import (
    GIB,
    _application_name,
    _linux_available_bytes,
    _mac_available_bytes,
    local_image_worker_running,
    local_renderer_status,
)


class HealthyResponse:
    def raise_for_status(self):
        pass


class HealthyClient:
    async def get(self, url, timeout):
        return HealthyResponse()


def test_mac_available_memory_includes_reclaimable_pages():
    vm_stat = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               100.
Pages active:                             900.
Pages inactive:                           200.
Pages speculative:                         20.
Pages purgeable:                           100.
"""
    assert _mac_available_bytes(vm_stat) == 320 * 16384


def test_linux_available_memory_uses_memavailable():
    assert _linux_available_bytes("MemTotal: 20000000 kB\nMemAvailable: 14680064 kB\n") == (
        14_680_064 * 1024
    )


def test_common_helper_processes_are_aggregated_under_their_app():
    assert _application_name(
        "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Helper"
    ) == "Google Chrome"
    assert _application_name(
        "/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper"
    ) == "Visual Studio Code"
    assert _application_name("/usr/local/bin/ollama runner") == "Ollama"


def test_gib_constant_is_binary_gigabyte():
    assert GIB == 1_073_741_824


def test_local_worker_process_detection(monkeypatch):
    monkeypatch.setattr(
        resource_service,
        "_run",
        lambda command: "/usr/bin/python workers/image_worker.py\n/usr/bin/python app.py\n",
    )
    assert local_image_worker_running() is True


def test_renderer_is_online_only_when_worker_and_comfyui_are_ready(monkeypatch):
    monkeypatch.setattr(resource_service, "local_image_worker_running", lambda: True)

    result = asyncio.run(local_renderer_status(HealthyClient()))

    assert result == {
        "online": True,
        "worker_running": True,
        "comfyui_online": True,
        "message": "Worker and ComfyUI are ready",
    }
