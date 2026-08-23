import subprocess
import threading
from typing import Any

from edge_agent.config import settings


class NetworkCommandError(RuntimeError):
    pass


_provisioning: dict[str, str | None] = {"state": "idle", "ssid": None, "error": None}
_provisioning_lock = threading.Lock()


def _nmcli(*args: str, timeout: int = 35, check: bool = True) -> str:
    result = subprocess.run(
        ["sudo", "-n", "nmcli", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        raise NetworkCommandError(result.stderr.strip() or "NetworkManager command failed")
    return result.stdout.strip()


def _split_terse(line: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            values.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    values.append("".join(current))
    return values


def network_status() -> dict[str, Any]:
    wlan = _device_status(settings.edge_wifi_interface)
    ethernet = _device_status(settings.edge_ethernet_interface)
    with _provisioning_lock:
        provisioning = dict(_provisioning)
    return {
        "wifi": wlan,
        "ethernet": ethernet,
        "hotspot": wlan["connection"] == settings.edge_hotspot_connection,
        "hotspot_ssid": settings.edge_hotspot_ssid,
        "direct_lan_address": settings.edge_direct_lan_address,
        "provisioning": provisioning,
    }


def _device_status(interface: str) -> dict[str, str | None]:
    output = _nmcli(
        "-t",
        "-f",
        "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS",
        "device",
        "show",
        interface,
    )
    fields: dict[str, str] = {}
    for line in output.splitlines():
        key, _, value = line.partition(":")
        if key and value and key not in fields:
            fields[key] = value
    return {
        "interface": interface,
        "state": fields.get("GENERAL.STATE"),
        "connection": fields.get("GENERAL.CONNECTION"),
        "address": fields.get("IP4.ADDRESS[1]"),
    }


def scan_wifi() -> list[dict[str, str | int | bool]]:
    output = _nmcli(
        "-t",
        "-f",
        "SSID,SIGNAL,SECURITY,IN-USE",
        "device",
        "wifi",
        "list",
        "ifname",
        settings.edge_wifi_interface,
        "--rescan",
        "yes",
        timeout=20,
    )
    networks: dict[str, dict[str, str | int | bool]] = {}
    for line in output.splitlines():
        values = _split_terse(line)
        if len(values) != 4 or not values[0]:
            continue
        ssid, signal, security, in_use = values
        item: dict[str, str | int | bool] = {
            "ssid": ssid,
            "signal": int(signal or 0),
            "security": security or "Open",
            "connected": in_use == "*",
        }
        if ssid not in networks or int(item["signal"]) > int(networks[ssid]["signal"]):
            networks[ssid] = item
    return sorted(networks.values(), key=lambda item: int(item["signal"]), reverse=True)


def connect_wifi(ssid: str, password: str) -> None:
    with _provisioning_lock:
        _provisioning.update(state="connecting", ssid=ssid, error=None)
    try:
        _nmcli("connection", "down", settings.edge_hotspot_connection, check=False)
        args = ["--wait", "30", "device", "wifi", "connect", ssid]
        if password:
            args.extend(["password", password])
        args.extend(["ifname", settings.edge_wifi_interface])
        _nmcli(*args, timeout=40)
    except (NetworkCommandError, subprocess.TimeoutExpired) as exc:
        with _provisioning_lock:
            _provisioning.update(state="failed", error=str(exc))
        return
    with _provisioning_lock:
        _provisioning.update(state="connected", error=None)
