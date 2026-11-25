import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from edge_agent.app import app
from edge_agent.state import EdgeState


@pytest.fixture
def mode_helper(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('network_mode', Path(__file__).parents[1] / 'systemd/network-mode.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setattr(helper, 'ROOT', tmp_path)
    monkeypatch.setattr(helper, 'STATE', tmp_path / 'state.json')
    monkeypatch.setattr(helper, 'DHCP', tmp_path / 'dnsmasq.conf')
    monkeypatch.setattr(helper, 'cancel_timer', lambda: None)
    current = {'mode': 'direct', 'ip': '192.168.10.80/24', 'fail_site': False}
    calls = []

    def run(*args):
        calls.append(args)
        if 'GENERAL.CONNECTION' in args:
            return helper.PROFILES[current['mode']]
        if 'ipv4.addresses' in args:
            return '10.55.1.1/24'
        if 'IP4.ADDRESS' in args:
            return current['ip']
        if 'up' in args:
            mode = next(key for key, value in helper.PROFILES.items() if value == args[-1])
            if mode == 'site' and current['fail_site']:
                raise RuntimeError('DHCP timed out')
            current['mode'] = mode
        return ''

    monkeypatch.setattr(helper, 'run', run)
    return helper, current, calls


def test_site_disables_dhcp_before_activation_and_arms_rollback(mode_helper):
    helper, current, calls = mode_helper
    helper.switch('site')
    assert 'dhcp-range' not in helper.DHCP.read_text()
    assert helper.read_state() == {'pending': True, 'previous': 'direct', 'target': 'site'}
    assert any('--on-active=180s' in call for call in calls)
    assert calls.index(('systemctl', 'restart', 'dnsmasq')) < calls.index(('nmcli', '--wait', '25', 'connection', 'up', helper.PROFILES['site']))
    helper.confirm()
    assert not helper.read_state()['pending']
    assert current['mode'] == 'site'


def test_timeout_or_reboot_restores_previous_profile_and_dhcp(mode_helper):
    helper, current, _ = mode_helper
    helper.switch('site')
    helper.rollback()
    assert current['mode'] == 'direct'
    assert 'dhcp-range=10.55.1.100,10.55.1.200' in helper.DHCP.read_text()
    assert helper.read_state()['result'] == 'rolled_back'


def test_failed_dhcp_activation_rolls_back_immediately(mode_helper):
    helper, current, _ = mode_helper
    current['fail_site'] = True
    with pytest.raises(RuntimeError):
        helper.switch('site')
    assert current['mode'] == 'direct'
    assert not helper.read_state()['pending']


def test_pending_change_cannot_be_replaced_or_confirmed_without_ip(mode_helper):
    helper, current, _ = mode_helper
    helper.switch('site')
    with pytest.raises(ValueError):
        helper.switch('direct')
    current['ip'] = ''
    with pytest.raises(ValueError):
        helper.confirm()
    assert helper.read_state()['pending']


@pytest.fixture
def edge_network(tmp_path, monkeypatch):
    state = EdgeState(tmp_path / 'edge.json')
    state.write({'paired': True, 'device_token': 'test-network-token', 'backend_url': 'http://old.test:8000'})
    state.device_id()
    monkeypatch.setattr('edge_agent.app.edge_state', state)
    monkeypatch.setattr('edge_agent.app.detection_manager.status', lambda: SimpleNamespace(running=False))
    return TestClient(app), state, {'Authorization': 'Bearer test-network-token'}


def test_network_changes_require_auth_and_idle_pipeline(edge_network, monkeypatch):
    client, _, headers = edge_network
    assert client.post('/network/ethernet', json={'mode': 'site'}).status_code == 403
    monkeypatch.setattr('edge_agent.app.detection_manager.status', lambda: SimpleNamespace(running=True))
    assert client.post('/network/ethernet', json={'mode': 'site'}, headers=headers).status_code == 409
    assert client.post('/network/wifi/connect', json={'ssid': 'Factory', 'password': 'testpassword'}, headers=headers).status_code == 409


def test_reconnect_saves_only_a_backend_that_proves_device_ownership(edge_network, monkeypatch):
    client, state, headers = edge_network
    def get(_client, url, **kwargs):
        assert kwargs['headers']['Authorization'] == 'Bearer test-network-token'
        return httpx.Response(200, json={'device_id': state.device_id()}, request=httpx.Request('GET', url))
    monkeypatch.setattr(httpx.Client, 'get', get)
    response = client.post('/network/reconnect', json={'backend_url': 'http://new.test:8000'}, headers=headers)
    assert response.status_code == 200
    assert state.read()['backend_url'] == 'http://new.test:8000'
    monkeypatch.setattr(httpx.Client, 'get', lambda _client, url, **kwargs: httpx.Response(403, request=httpx.Request('GET', url)))
    assert client.post('/network/reconnect', json={'backend_url': 'http://other.test:8000'}, headers=headers).status_code == 409
    assert state.read()['backend_url'] == 'http://new.test:8000'


def test_confirm_requires_new_ethernet_address(edge_network, monkeypatch):
    client, _, headers = edge_network
    monkeypatch.setattr('edge_agent.app.network_status', lambda: {'ethernet': {'address': '192.168.10.80/24'}})
    confirmed = []
    monkeypatch.setattr('edge_agent.app.confirm_ethernet_mode', lambda: confirmed.append(True))
    assert client.post('/network/ethernet/confirm', headers=headers).status_code == 409
    response = client.post('http://192.168.10.80/network/ethernet/confirm', headers=headers)
    assert response.status_code == 200 and confirmed == [True]


def test_unconfirmed_network_cannot_start_detection(edge_network, monkeypatch):
    client, _, headers = edge_network
    monkeypatch.setattr('edge_agent.app.ethernet_mode_status', lambda: {'pending': True, 'available': True})
    response = client.post('/detection/start', json={'session_id': 'test', 'run_id': 'run'}, headers=headers)
    assert response.status_code == 409
    assert 'Confirm' in response.json()['detail']
