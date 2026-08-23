#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
hotspot_name="ErgoQuipt Setup"
hotspot_ssid="${EDGE_HOTSPOT_SSID:-ErgoQuipt-CAM01}"
hotspot_password="${ERGOQUIPT_HOTSPOT_PASSWORD:-$(openssl rand -hex 7)}"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y dnsmasq

nmcli connection delete "ErgoQuipt Direct LAN" >/dev/null 2>&1 || true
nmcli connection add type ethernet ifname eth0 con-name "ErgoQuipt Direct LAN" \
  ipv4.method manual ipv4.addresses 10.55.0.1/24 ipv4.never-default yes \
  ipv6.method disabled connection.autoconnect yes connection.autoconnect-priority 100

nmcli connection delete "$hotspot_name" >/dev/null 2>&1 || true
nmcli connection add type wifi ifname wlan0 con-name "$hotspot_name" ssid "$hotspot_ssid"
nmcli connection modify "$hotspot_name" \
  802-11-wireless.mode ap 802-11-wireless.band bg \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$hotspot_password" \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled \
  connection.autoconnect no

install -m 0644 "$repo/systemd/ergoquipt-wifi-fallback.service" /etc/systemd/system/
install -m 0755 "$repo/systemd/ergoquipt-wifi-fallback.sh" /usr/local/sbin/ergoquipt-wifi-fallback
printf 'admin ALL=(root) NOPASSWD: /usr/bin/nmcli\n' >/etc/sudoers.d/ergoquipt-network
chmod 0440 /etc/sudoers.d/ergoquipt-network
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
nmcli connection up "ErgoQuipt Direct LAN"

printf 'Hotspot SSID: %s\nHotspot password: %s\n' "$hotspot_ssid" "$hotspot_password"
