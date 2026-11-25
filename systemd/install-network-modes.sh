#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
nmcli connection show 'ERGoSIGHT Direct LAN' >/dev/null
if ! nmcli connection show 'ERGoSIGHT Site LAN' >/dev/null 2>&1; then
  nmcli connection add type ethernet ifname eth0 con-name 'ERGoSIGHT Site LAN' \
    ipv4.method auto ipv6.method auto connection.autoconnect no
fi
install -o root -g root -m 0755 "$repo/systemd/network-mode.py" /usr/local/sbin/ergosight-network-mode
install -o root -g root -m 0440 "$repo/systemd/ergosight-network-mode.sudoers" /etc/sudoers.d/ergosight-network-mode
visudo -cf /etc/sudoers.d/ergosight-network-mode
install -m 0644 "$repo/systemd/ergosight-network-restore.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable ergosight-network-restore.service
printf 'Network modes installed; active connection unchanged.\n'
