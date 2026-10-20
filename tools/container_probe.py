"""Check the built hosted image with a disposable disk and synthetic credentials.

Requires Docker and the release-atlas:hosted-check image. No provider calls.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
name = 'atlas-hosted-check-' + uuid.uuid4().hex[:10]
volume = name + '-data'
TOKEN = 'synthetic-gateway-0123456789abcdef0123456789'
ACCESS = 'synthetic-access-0123456789abcdef0123456789'


def docker(*args):
    result = subprocess.run(['docker', *args], text=True, capture_output=True, check=True)
    return result.stdout.strip()


def main():
    report = {}
    docker('volume', 'create', volume)
    try:
        settings = {
            'ATLAS_GATEWAY_TOKEN': TOKEN, 'ATLAS_ACCESS_CODE': ACCESS,
            'OPENAI_API_KEY': 'synthetic-not-a-real-key',
            'ATLAS_SITE_ORIGIN': 'https://atlas.example',
            'ATLAS_BACKEND_ORIGIN': 'https://backend.example',
            'ATLAS_DATA_DIR': '/data', 'PORT': '10000',
            'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
        }
        args = ['docker', 'run', '-d', '--name', name, '--memory', '512m', '--cpus', '0.5',
                '-p', '127.0.0.1::10000', '-v', volume + ':/data']
        for key in settings:
            args.extend(['-e', key])
        args.extend(['release-atlas:hosted-check', 'python', '-m', 'backend.hosted'])
        subprocess.run(args, env={**os.environ, **settings}, capture_output=True, check=True)
        address = docker('port', name, '10000/tcp')
        base = 'http://' + address
        with httpx.Client(base_url=base, trust_env=False, timeout=30,
                          headers={'Host': 'backend.example', 'Origin': 'https://atlas.example'}) as client:
            def ready():
                for _ in range(200):
                    try:
                        if client.get('/api/health').status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
                raise AssertionError('Hosted container failed to start')

            def login():
                response = client.post('/api/login', json={'name': 'Synthetic reviewer', 'passcode': ACCESS})
                response.raise_for_status()
                cookie = response.headers['set-cookie']
                assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
                client.headers['Cookie'] = cookie.split(';')[0]

            ready()
            assert client.get('/api/state').status_code == 403
            client.headers['X-Atlas-Gateway-Token'] = TOKEN
            assert client.get('/api/state').status_code == 401
            login()
            html = client.get('/').text
            state = client.post('/api/demo', json={'revision': 0})
            state.raise_for_status()
            assert state.json()['analysis'] and state.json()['sources']
            reviewed = client.put('/api/claims/' + state.json()['claims'][0]['id'] + '/review', json={
                'revision': state.json()['revision'], 'status': 'applicable', 'note': 'Persistent container check'})
            reviewed.raise_for_status()
            before = client.get('/api/export').json()
            for secret in [TOKEN, ACCESS, settings['OPENAI_API_KEY']]:
                assert secret not in html and secret not in json.dumps(before)
            memory = json.loads(docker('stats', name, '--no-stream', '--format', '{{json .}}'))['MemUsage']
            docker('restart', name)
            client.base_url = 'http://' + docker('port', name, '10000/tcp')
            ready()
            assert client.get('/api/state').status_code == 401
            login()
            assert client.get('/api/export').json() == before
            health = docker('exec', name, 'python', '-c',
                "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:10000/api/health').status == 200")
            assert docker('exec', name, 'id', '-u') == '10001'
            report = {'result': 'PASS', 'image': 'release-atlas:hosted-check',
                      'checks': ['non-root startup', '512 MB memory limit', 'custom PORT health probe',
                                 'gateway and user authentication', 'real analysis', 'evidence review',
                                 'SQLite data preserved across container restart', 'sessions expire at restart',
                                 'no credentials in live HTML or exported workspace'],
                      'sampled_memory': memory, 'paid_api_calls': 0,
                      'limits': ['Docker Desktop Linux arm64, not Render infrastructure',
                                 'One small synthetic workspace, not a capacity guarantee',
                                 'No real model request or browser interaction']}
        (ROOT / 'validation/hosted-container-results.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    main()
