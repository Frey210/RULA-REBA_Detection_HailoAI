#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install -d -m 0755 /etc/systemd/journald.conf.d
target=/etc/systemd/journald.conf.d/ergosight.conf
if [[ -f "$target" ]]; then
  backup="/var/backups/ergosight-journal-$(date +%Y%m%d-%H%M%S)"
  install -d -m 0700 "$backup"
  cp "$target" "$backup/"
fi
install -o root -g root -m 0644 "$repo/systemd/ergosight-journal.conf" "$target"
systemd-tmpfiles --create --prefix /var/log/journal
systemctl restart systemd-journald
journalctl --flush
systemctl is-active systemd-journald
journalctl --disk-usage
