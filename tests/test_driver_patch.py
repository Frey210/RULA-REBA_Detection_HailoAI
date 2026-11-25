from pathlib import Path
import shutil
import subprocess
import pytest


def test_driver_patch_is_valid_and_only_adds_balanced_lock_paths():
    git = shutil.which('git')
    if not git:
        pytest.skip('git required for unified diff validation')
    patch = Path(__file__).parents[1] / 'systemd/patches/hailo-4.23-pcie-mmap-lock.patch'
    result = subprocess.run([git, 'apply', '--numstat', str(patch.resolve())],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '4\t0\tlinux/vdma/memory.c'
    added = [line for line in patch.read_text().splitlines() if line.startswith('+') and not line.startswith('+++')]
    assert sum('mmap_read_lock(' in line for line in added) == 1
    assert sum('mmap_read_unlock(' in line for line in added) == 3
