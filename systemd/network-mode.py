#!/usr/bin/python3
"""Root-owned Ethernet profile switcher; no repository imports or user commands."""
import argparse
import ipaddress
import json
from pathlib import Path
import subprocess

ROOT = Path('/var/lib/ergosight-network')
STATE = ROOT / 'transition.json'
DHCP = Path('/etc/dnsmasq.d/ergoquipt-direct-lan.conf')
PROFILES = {'direct': 'ERGoSIGHT Direct LAN', 'site': 'ERGoSIGHT Site LAN'}
TIMER = 'ergosight-network-rollback'


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=40).stdout.strip()


def read_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def write_state(state):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state))
    temporary.chmod(0o600)
    temporary.replace(STATE)


def current_mode():
    profile = run('nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', 'eth0')
    active = next((mode for mode, name in PROFILES.items() if profile == name), None)
    if active:
        return active
    # Wi-Fi remains a setup path when the Ethernet cable is unplugged.
    return 'site' if run('nmcli', '-g', 'connection.autoconnect', 'connection', 'show', PROFILES['site']) == 'yes' else 'direct'


def apply(mode):
    config = 'interface=eth0\nbind-dynamic\nport=0\n'
    if mode == 'direct':
        address = ipaddress.IPv4Interface(run('nmcli', '-g', 'ipv4.addresses', 'connection', 'show', PROFILES[mode]))
        if address.network.prefixlen != 24 or int(address.ip) % 256 != 1:
            raise ValueError('Direct LAN profile must use .1/24')
        prefix = str(address.ip).rsplit('.', 1)[0]
        config += f'dhcp-range={prefix}.100,{prefix}.200,255.255.255.0,12h\ndhcp-option=3\ndhcp-option=6\n'
    # Stop DHCP before enabling the site profile; never serve leases on the location LAN.
    DHCP.write_text(config)
    run('systemctl', 'restart', 'dnsmasq')
    for key, profile in PROFILES.items():
        run('nmcli', 'connection', 'modify', profile, 'connection.autoconnect', 'yes' if key == mode else 'no')
    run('nmcli', '--wait', '25', 'connection', 'up', PROFILES[mode])


def cancel_timer():
    subprocess.run(['systemctl', 'stop', TIMER + '.timer'], capture_output=True, timeout=10)
    subprocess.run(['systemctl', 'reset-failed', TIMER + '.service'], capture_output=True, timeout=10)


def rollback():
    state = read_state()
    if state.get('pending'):
        apply(state['previous'])
        write_state({'pending': False, 'result': 'rolled_back'})


def switch(mode):
    if read_state().get('pending'):
        raise ValueError('Confirm or wait for the pending network change first')
    previous = current_mode()
    if previous not in PROFILES:
        raise ValueError('Current Ethernet profile is not managed by ERGoSIGHT')
    if previous == mode:
        return
    cancel_timer()
    write_state({'pending': True, 'previous': previous, 'target': mode})
    try:
        run('systemd-run', '--collect', '--unit=' + TIMER, '--on-active=180s',
            '--timer-property=AccuracySec=1s', '/usr/local/sbin/ergosight-network-mode', 'rollback')
        apply(mode)
    except Exception:
        rollback()
        raise


def confirm():
    state = read_state()
    if state.get('pending'):
        if current_mode() != state['target'] or not run('nmcli', '-g', 'IP4.ADDRESS', 'device', 'show', 'eth0'):
            raise ValueError('Ethernet has not obtained an IPv4 address')
        write_state({'pending': False, 'result': 'confirmed'})
        cancel_timer()


def main():
    import fcntl
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'site', 'direct', 'confirm', 'rollback'])
    action = parser.parse_args().action
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (ROOT / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == 'status':
            print(json.dumps({'pending': False, **read_state(), 'mode': current_mode(), 'available': True}))
        elif action in PROFILES:
            switch(action)
        elif action == 'confirm':
            confirm()
        else:
            rollback()


if __name__ == '__main__':
    main()
