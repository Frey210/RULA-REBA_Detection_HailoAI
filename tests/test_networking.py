from edge_agent.networking import _split_terse
from edge_agent.schemas import WifiConnectRequest


def test_nmcli_parser_and_wifi_validation() -> None:
    assert _split_terse(r"Factory\:Floor:82:WPA2:*") == ["Factory:Floor", "82", "WPA2", "*"]
    assert WifiConnectRequest(ssid=" Factory WiFi ", password="password123").ssid == "Factory WiFi"
