"""Verify the scheduler's stop/restart behavior without claiming Docker validation."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('failure,exit_code', [('', 0), ('run', 17), ('config', 17)])
def test_backup_wrapper_restores_writers_on_backup_failure(tmp_path, failure, exit_code):
    binary = tmp_path / 'bin'
    binary.mkdir()
    docker = binary / 'docker'
    implementation = tmp_path / 'docker.py'
    docker.write_text('#!/bin/sh\nexec "$MOCK_PYTHON" "$MOCK_DOCKER" "$@"\n')
    implementation.write_text('''import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if os.environ['FAIL_OPERATION'] and os.environ['FAIL_OPERATION'] in sys.argv:
    sys.exit(17)
''')
    docker.chmod(0o700)
    key = tmp_path / 'separate key'
    key.write_bytes(b'x' * 32)
    destination = tmp_path / 'backup directory'
    destination.mkdir()
    log = tmp_path / 'commands.jsonl'
    env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
           'PILOT_BACKUP_KEY': str(key), 'PILOT_BACKUP_DIRECTORY': str(destination),
           'PILOT_DEPLOYMENT_DIR': str(tmp_path), 'CALL_LOG': str(log), 'FAIL_OPERATION': failure,
           'MOCK_PYTHON': sys.executable, 'MOCK_DOCKER': str(implementation)}
    script = Path(__file__).resolve().parents[2] / 'deployment' / 'backup.sh'
    result = subprocess.run(['/bin/sh', str(script)], env=env, capture_output=True, text=True)
    assert result.returncode == exit_code, result.stderr
    calls = [json.loads(row) for row in log.read_text().splitlines()]
    if failure == 'config':
        assert not any('stop' in call or 'run' in call or 'up' in call for call in calls)
    else:
        assert any(call[-3:] == ['stop', 'app', 'worker'] for call in calls)
        assert calls[-1][-4:] == ['up', '-d', 'app', 'worker']
        run = next(call for call in calls if 'run' in call)
        assert str(key) + ':/run/backup.key:ro' in run
        assert str(destination) + ':/backups' in run
        assert '--services-stopped' in run
