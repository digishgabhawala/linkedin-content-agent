from app.services.resource_service import (
    GIB,
    _application_name,
    _linux_available_bytes,
    _mac_available_bytes,
)


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
