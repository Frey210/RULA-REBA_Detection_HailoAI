#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Separate direct cables must not advertise the same subnet on multiple laptop ports.
cam_id="${EDGE_CAM_ID:-$(sed -n 's/^EDGE_CAM_ID=//p' "$repo/.env" 2>/dev/null | tail -1)}"
cam_id="${cam_id:-CAM_01}"
if [[ ! "$cam_id" =~ ^CAM_([0-9]{1,3})$ ]]; then
  printf 'EDGE_CAM_ID must be CAM_01 through CAM_254\n' >&2
  exit 1
fi
camera_number=$((10#${BASH_REMATCH[1]}))
if ((camera_number < 1 || camera_number > 254)); then
  printf 'Camera number must be 1 through 254\n' >&2
  exit 1
fi
direct_address="${EDGE_DIRECT_LAN_ADDRESS:-10.55.$camera_number.1/24}"
direct_prefix=$(python3 -c 'import ipaddress,sys; a=ipaddress.IPv4Interface(sys.argv[1]); assert a.is_private and a.network.prefixlen == 24 and int(a.ip) % 256 == 1, "Use a private IPv4 .1/24 address"; print(str(a.ip).rsplit(".",1)[0])' "$direct_address")
if [[ "${1:-}" == '--print-direct-lan' ]]; then
  printf '%s\n%s\n' "$direct_address" "$direct_prefix"
  exit 0
fi
direct_name="ERGoSIGHT Direct LAN"
hotspot_name="ERGoSIGHT Setup"
hotspot_ssid="${EDGE_HOTSPOT_SSID:-ERGoSIGHT-CAM01}"
hotspot_password="${ERGOSIGHT_HOTSPOT_PASSWORD:-${ERGOQUIPT_HOTSPOT_PASSWORD:-$(openssl rand -hex 7)}}"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y dnsmasq

nmcli connection delete "ErgoQuipt Direct LAN" >/dev/null 2>&1 || true
nmcli connection delete "$direct_name" >/dev/null 2>&1 || true
nmcli connection add type ethernet ifname eth0 con-name "$direct_name" \
  ipv4.method manual ipv4.addresses "$direct_address" ipv4.never-default yes \
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

cat >/etc/dnsmasq.d/ergoquipt-direct-lan.conf <<EOF
interface=eth0
bind-dynamic
port=0
dhcp-range=$direct_prefix.100,$direct_prefix.200,255.255.255.0,12h
dhcp-option=3
dhcp-option=6
EOF

systemctl daemon-reload
systemctl enable dnsmasq ergoquipt-wifi-fallback.service
systemctl restart dnsmasq ergoquipt-wifi-fallback.service
nmcli connection up "$direct_name"

printf 'Hotspot SSID: %s\nHotspot password: %s\n' "$hotspot_ssid" "$hotspot_password"
