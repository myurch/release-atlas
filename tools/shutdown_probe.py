"""Real loopback shutdown check with an open SSE connection and isolated data."""
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    runs = []
    for stop_signal in (signal.SIGINT, signal.SIGTERM):
        with tempfile.TemporaryDirectory(prefix='atlas-shutdown-') as data:
            with socket.socket() as available:
                available.bind(('127.0.0.1', 0))
                port = available.getsockname()[1]
            env = {**os.environ, 'ATLAS_PORT': str(port), 'ATLAS_DATA_DIR': data,
                   'ATLAS_HOST': '127.0.0.1', 'ATLAS_ORIGINS': f'http://127.0.0.1:{port}',
                   'ATLAS_AUTH_ENABLED': '0', 'ATLAS_LLM_KIND': 'openai',
                   'ATLAS_LLM_BASE': 'https://api.openai.com/v1', 'ATLAS_LLM_MODEL': 'gpt-6-luna',
                   'OPENAI_API_KEY': '', 'ATLAS_LLM_KEY': '',
                   'PYTHONDONTWRITEBYTECODE': '1', 'RELEASE_ATLAS_NO_BROWSER': '1'}
            command = ['sh', 'run-release-atlas-macos-intel.sh'] if platform.system() == 'Darwin' and platform.machine() == 'x86_64' else [sys.executable, '-m', 'backend']
            stream = None
            with tempfile.TemporaryFile() as log:
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=log, start_new_session=True)
                try:
                    deadline = time.monotonic()+15
                    while True:
                        try:
                            stream = urllib.request.urlopen(f'http://127.0.0.1:{port}/api/events', timeout=2)
                            break
                        except OSError:
                            if process.poll() is not None or time.monotonic() >= deadline:
                                raise AssertionError('Server failed to start')
                            time.sleep(0.1)
                    assert stream.readline().startswith(b'data: ')
                    start = time.monotonic()
                    process.send_signal(stop_signal)
                    process.wait(timeout=8)
                    elapsed = round(time.monotonic()-start, 3)
                    # Keep the client open through process exit: closing it must not be required.
                    with socket.socket() as released:
                        assert released.connect_ex(('127.0.0.1', port)) != 0
                    log.seek(0)
                    output = log.read().decode(errors='replace')
                    assert 'timeout graceful shutdown exceeded' not in output
                    assert 'Application shutdown complete.' in output
                    runs.append({'signal': stop_signal.name, 'elapsed_seconds': elapsed,
                                 'open_sse_client': True, 'port_released': True,
                                 'forced_cancellation': False, 'launcher': command})
                finally:
                    if stream:
                        stream.close()
                    if process.poll() is None:
                        process.kill()
                        process.wait()
    report = {'result': 'PASS', 'runs': runs,
              'scope': 'Real processes and HTTP/SSE; temporary data; no model calls or credentials',
              'limits': ['Idle SSE shutdown tested; model requests retain a five-second cancellation fallback']}
    (ROOT/'validation/shutdown-results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
