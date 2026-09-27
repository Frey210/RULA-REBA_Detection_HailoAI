#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
direct_name="ERGoSIGHT Direct LAN"
hotspot_name="ERGoSIGHT Setup"
hotspot_ssid="${EDGE_HOTSPOT_SSID:-ERGoSIGHT-CAM01}"
hotspot_password="${ERGOSIGHT_HOTSPOT_PASSWORD:-${ERGOQUIPT_HOTSPOT_PASSWORD:-$(openssl rand -hex 7)}}"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y dnsmasq

nmcli connection delete "ErgoQuipt Direct LAN" >/dev/null 2>&1 || true
nmcli connection delete "$direct_name" >/dev/null 2>&1 || true
nmcli connection add type ethernet ifname eth0 con-name "$direct_name" \
  ipv4.method manual ipv4.addresses 10.55.0.1/24 ipv4.never-default yes \
  ipv6.method disabled connection.autoconnect yes connection.autoconnect-priority 100

nmcli connection delete "ErgoQuipt Setup" >/dev/null 2>&1 || true
nmcli connection delete "$hotspot_name" >/dev/null 2>&1 || true
nmcli connection add type wifi ifname wlan0 con-name "$hotspot_name" ssid "$hotspot_ssid"
nmcli connection modify "$hotspot_name" \
  802-11-wireless.mode ap 802-11-wireless.band bg \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$hotspot_password" \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled \
  connection.autoconnect no

install -m 0644 "$repo/systemd/ergoquipt-wifi-fallback.service" /etc/systemd/system/
install -m 0755 "$repo/systemd/ergoquipt-wifi-fallback.sh" /usr/local/sbin/ergoquipt-wifi-fallback
install -m 0440 "$repo/systemd/ergoquipt-network.sudoers" /etc/sudoers.d/ergoquipt-network
visudo -cf /etc/sudoers.d/ergoquipt-network

cat >/etc/dnsmasq.d/ergoquipt-direct-lan.conf <<'EOF'
interface=eth0
bind-dynamic
port=0
dhcp-range=10.55.0.100,10.55.0.200,255.255.255.0,12h
dhcp-option=3
dhcp-option=6
EOF

systemctl daemon-reload
systemctl enable dnsmasq ergoquipt-wifi-fallback.service
systemctl restart dnsmasq ergoquipt-wifi-fallback.service
nmcli connection up "$direct_name"

printf 'Hotspot SSID: %s\nHotspot password: %s\n' "$hotspot_ssid" "$hotspot_password"
