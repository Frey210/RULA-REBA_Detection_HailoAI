#!/usr/bin/env bash
# PCIe-only 4.23.0 backport; no kernel, EEPROM, firmware or userspace upgrade.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kernel=$(uname -r)
test "$(id -u)" = 0
test "$(modinfo -F version hailo_pci)" = 4.23.0
test -d "/lib/modules/$kernel/build"
source=/usr/src/hailort-pcie-driver
test -f "$source/linux/pcie/Kbuild"
require_idle() {
  (cd "$repo" && .venv/bin/python - <<'PY'
import json
from pathlib import Path
import httpx
state = json.loads(Path('data/edge_state.json').read_text())
with httpx.Client(trust_env=False, timeout=3) as client:
    response = client.get('http://127.0.0.1:8765/detection/status',
                          headers={'Authorization': 'Bearer ' + state.get('device_token', '')})
    response.raise_for_status()
    if response.json().get('running'):
        raise SystemExit('Stop detection before installing the driver backport')
PY
  )
}
require_idle
# The upstream PCIe fix does not cover the integrated_nnc MMIO build.
if grep -Eq 'HAILO_SUPPORT_MMIO_DMA_MAPPING' "$source/linux/pcie/Kbuild"; then
  printf 'Refusing an MMIO driver build.\n' >&2
  exit 1
fi
override="/lib/modules/$kernel/updates/ergosight/hailo_pci.ko"
test ! -e "$override" || { printf 'A local override already exists; inspect it before reinstalling.\n' >&2; exit 1; }
backup="/var/backups/ergosight-hailo-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "$backup"
original=$(modinfo -n hailo_pci)
cp -a "$original" "$backup/"
cp "$source/linux/vdma/memory.c" "$backup/memory.c.original"
modinfo hailo_pci >"$backup/module-original.txt"
work=$(mktemp -d /var/tmp/ergosight-hailo-build.XXXXXX)
cp -a "$source" "$work/source"
patch --batch --fuzz=0 --directory="$work/source" -p1 <"$repo/systemd/patches/hailo-4.23-pcie-mmap-lock.patch"
make -C "/lib/modules/$kernel/build" M="$work/source/linux/pcie" -j2 modules >"$backup/build.log" 2>&1 || {
  tail -50 "$backup/build.log"
  exit 1
}
built="$work/source/linux/pcie/hailo_pci.ko"
test "$(modinfo -F version "$built")" = 4.23.0
test "$(modinfo -F vermagic "$built" | cut -d' ' -f1)" = "$kernel"
was_active=$(systemctl is-active ergoquipt-edge-agent || true)
created=no
rollback() {
  trap - ERR
  if [[ "$created" == yes ]]; then
    modprobe -r hailo_pci || true
    rm -f -- "$override"
    depmod -a "$kernel"
  fi
  modprobe hailo_pci || true
  if [[ "$was_active" == active ]]; then systemctl start ergoquipt-edge-agent || true; fi
  printf 'Installation aborted; original module remains available. Backup: %s\n' "$backup" >&2
  exit 1
}
trap rollback ERR
require_idle
systemctl stop ergoquipt-edge-agent
modprobe -r hailo_pci
install -D -m 0644 "$built" "$override"
created=yes
depmod -a "$kernel"
test "$(modinfo -n hailo_pci)" = "$override"
modprobe hailo_pci
hailortcli fw-control identify
if [[ "$was_active" == active ]]; then systemctl start ergoquipt-edge-agent; fi
sha256sum "$override" >"$backup/installed-sha256.txt"
printf 'Installed 4.23.0 PCIe mmap-lock backport. Backup: %s\nBuild: %s\n' "$backup" "$work"
