#!/usr/bin/env bash
set -u

connection="${EDGE_HOTSPOT_CONNECTION:-ERGoSIGHT Setup}"
interface="${EDGE_WIFI_INTERFACE:-wlan0}"

sleep "${EDGE_WIFI_FALLBACK_SECONDS:-60}"
while true; do
  active="$(nmcli -g GENERAL.CONNECTION device show "$interface" 2>/dev/null || true)"
  if [[ -z "$active" || "$active" == "--" ]]; then
    nmcli connection up "$connection" >/dev/null 2>&1 || true
  fi
  sleep 15
done
