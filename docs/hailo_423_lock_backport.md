# Hailo PCIe 4.23.0 mmap-lock Backport

This is an administrator hotfix for a reproduced CAM_03 kernel warning storm,
not an Electron or pairing change. It is limited to the default PCIe build of
Hailo driver 4.23.0. The integrated_nnc/MMIO path is outside this patch's scope.

The installed 4.23.0 source called `find_vma()` without holding the mmap read
lock. The backport holds the lock through DMA-BUF classification and file
reference acquisition, releasing it on both early errors and the normal exit.
References: [Hailo repository PR 44](https://github.com/hailo-ai/hailort-drivers/pull/44),
[VMA lifetime follow-up PR 65](https://github.com/hailo-ai/hailort-drivers/pull/65).
These pull requests are not represented as a merged vendor release.

## Installation

Stop assessments first. On an existing Pi installation with matching running
kernel headers and `/usr/src/hailort-pcie-driver` source:

```bash
sudo bash systemd/install-hailo-423-lock-fix.sh
```

The script checks driver version and idle detection, backs up the original
module/source, patches a private build copy, and builds against the running
kernel. It does not edit the package-managed source. Before activation it
checks version/vermagic and idle detection again. The agent is stopped for
module replacement and restarted if originally active. A failed activation
attempt removes the new override and attempts to reload the original module.

The override is installed at:

`/lib/modules/<running-kernel>/updates/ergosight/hailo_pci.ko`

Original package module remains under `kernel/drivers/misc/`. Backups and build
logs are under `/var/backups/ergosight-hailo-<timestamp>/`; the private build
directory is retained under `/var/tmp/ergosight-hailo-build.*` for inspection.
An existing override is not overwritten automatically.

No kernel image, EEPROM, boot configuration, runtime library or Hailo firmware
is upgraded. The module still reports version 4.23.0, so inspect module path,
loaded srcversion and recorded checksum to distinguish this local backport.

## Validation on CAM_03, 2026-11-25

- Raspberry Pi 5, kernel `6.18.50+rpt-rpi-2712`, Hailo-8/firmware 4.23.0.
- User reported official Raspberry Pi 27W/5A power supply.
- Before: diagnostic session `SESSION_20261125_004` lost LAN and Wi-Fi after
  approximately 40 seconds. Persistent kernel journal recorded 2,872 warnings
  from `find_vma` through `hailo_vdma_buffer_map` in `hailo_pci`.
- After: `SESSION_20261125_005` completed 60 seconds, 30 ready-state polls,
  98-336 ms frame age, 136 authenticated events, then stopped successfully.
- A 95-sample hardware observation recorded carrier=1 throughout,
  `throttled=0x0`, temperature 54.9-62.6 C and EXT5V 4.9178-5.14828 V.
- Current boot had zero matching VMA warnings after the test.
- Loaded module srcversion: `30DDE7EC2257F8EDD3C0D78`.
- Original module backup: `/var/backups/ergosight-hailo-20261125-215839/`.
- Module resolution selects the override. No Hailo module was found in the
  current `initramfs_2712`, so that image was not regenerated.

Only CAM_03 received this module hotfix. Other cameras require separate source
inspection and acceptance tests. A one-minute successful retest is not a soak,
multi-camera, reboot, lockdep or broad memory-race certification. It also does
not exclude unrelated hardware problems or transients between sampled voltages.

## Maintenance and Rollback

The override is specific to this kernel and 4.23.0 runtime/firmware. A later
kernel needs a matching build; a coordinated Hailo stack upgrade needs review
and removal of the old override before it can mask a newer package module.
Do not assume a Windows installer applies this Pi kernel-module hotfix.

An administrator can stop the agent, unload `hailo_pci`, remove only the exact
override file above, run `depmod -a` and reload the original module, then start
the agent. Confirm no other process is using Hailo before unloading. Do not
delete the package-managed module or unrelated files in `/lib/modules`.

For subsequent incidents, optional bounded persistent logging can be enabled
with `sudo bash systemd/install-diagnostics.sh`. It uses at most 100 MB of
system journal, seven-day retention and ten-second sync; no automatic reboot
or detection is enabled by that diagnostic configuration.
