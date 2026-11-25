import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('cam_id,override,expected', [
    ('CAM_01', '', '10.55.1.1/24'),
    ('CAM_02', '', '10.55.2.1/24'),
    ('CAM_03', '', '10.55.3.1/24'),
    ('CAM_254', '', '10.55.254.1/24'),
    ('CAM_02', '192.168.90.1/24', '192.168.90.1/24'),
    ('CAM_00', '', None),
    ('CAM_255', '', None),
    ('other', '', None),
    ('CAM_02', '10.55.2.10/24', None),
    ('CAM_02', '8.8.8.1/24', None),
    ('CAM_02', '127.0.0.1/24', None),
    ('CAM_02', '169.254.1.1/24', None),
])
def test_direct_lan_install_address(cam_id, override, expected):
    git_bash = Path('C:/Program Files/Git/bin/bash.exe')
    bash = str(git_bash) if git_bash.exists() else shutil.which('bash')
    if not bash:
        pytest.skip('bash required for network installer test')
    script = Path(__file__).resolve().parents[1] / 'systemd/install-networking.sh'
    result = subprocess.run([bash, str(script), '--print-direct-lan'],
                            env={**os.environ, 'EDGE_CAM_ID': cam_id, 'EDGE_DIRECT_LAN_ADDRESS': override},
                            capture_output=True, text=True, timeout=15)
    if expected is None:
        assert result.returncode != 0
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[0] == expected
