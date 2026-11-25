from edge_agent.networking import _split_terse
from edge_agent.schemas import WifiConnectRequest
from edge_agent import networking


def test_nmcli_parser_and_wifi_validation() -> None:
    assert _split_terse(r"Factory\:Floor:82:WPA2:*") == ["Factory:Floor", "82", "WPA2", "*"]
    assert WifiConnectRequest(ssid=" Factory WiFi ", password="password123").ssid == "Factory WiFi"


def test_network_status_reports_actual_direct_lan_address(monkeypatch):
    monkeypatch.setattr(networking, '_device_status', lambda interface: {
        'interface': interface, 'connection': 'ERGoSIGHT Direct LAN',
        'state': '100', 'address': '10.55.2.1/24' if interface == networking.settings.edge_ethernet_interface else None,
    })
    assert networking.network_status()['direct_lan_address'] == '10.55.2.1/24'
