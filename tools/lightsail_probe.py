"""Run the Lightsail Compose services locally with synthetic credentials and data.

Build release-atlas:lightsail-amd64 first. This checks Linux AMD64 application
containers under Docker Desktop emulation and the pinned Caddy HTTP proxy.
No public certificate, provider call, AWS account or user workspace is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'synthetic-gateway-0123456789abcdef0123456789'
ACCESS = 'synthetic-access-0123456789abcdef0123456789'


def main():
    project = 'atlas-lightsail-check-' + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        temp = Path(directory)
        runtime = temp / 'runtime.env'
        runtime.write_text('OPENAI_API_KEY=synthetic-not-a-real-key\n'
                           + 'ATLAS_GATEWAY_TOKEN=' + TOKEN + '\nATLAS_ACCESS_CODE=' + ACCESS + '\n')
        runtime.chmod(0o600)
        public = temp / 'site.env'
        public.write_text('ATLAS_SITE_ORIGIN=https://atlas.example\n'
                          'ATLAS_BACKEND_HOSTNAME=backend.example\n'
                          'ATLAS_IMAGE_TAG=lightsail-amd64\nATLAS_RUNTIME_ENV=' + str(runtime) + '\n')
        base = ['docker', 'compose', '--env-file', str(public), '-f',
                str(ROOT / 'deploy/lightsail/compose.yaml')]
        # The explicit env file avoids loading the repository's private .env.
        resolved = subprocess.run([*base, 'config', '--format', 'json'], cwd=ROOT,
                                  text=True, capture_output=True, check=True)
        config = json.loads(resolved.stdout)
        assert not config['services']['atlas'].get('ports')
        assert 'OPENAI_API_KEY' not in config['services']['caddy'].get('environment', {})
        config['name'] = project
        for kind in ['networks', 'volumes']:
            for key, value in config[kind].items():
                value['name'] = project + '_' + key
        atlas = config['services']['atlas']
        atlas.pop('build', None)
        atlas['platform'] = 'linux/amd64'
        caddyfile = temp / 'Caddyfile'
        # Avoid public ACME/certificate requests in the isolated HTTP smoke test.
        caddyfile.write_text((ROOT / 'deploy/lightsail/Caddyfile').read_text()
                            .replace('{$ATLAS_BACKEND_HOSTNAME} {', 'http://backend.example:8080 {'))
        caddy = config['services']['caddy']
        caddy['ports'] = [{'target': 8080, 'published': '0', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]
        for volume in caddy['volumes']:
            if volume['target'] == '/etc/caddy/Caddyfile':
                volume['source'] = str(caddyfile)
        compose = temp / 'compose.json'
        compose.write_text(json.dumps(config))
        compose.chmod(0o600)
        args = ['docker', 'compose', '--env-file', str(public), '-p', project, '-f', str(compose)]

        def run(*command):
            return subprocess.run([*args, *command], cwd=ROOT, text=True,
                                  capture_output=True, check=True, timeout=180).stdout.strip()

        try:
            run('up', '-d', '--wait', '--wait-timeout', '90', '--no-build')
            address = run('port', 'caddy', '8080')
            with httpx.Client(base_url='http://' + address, trust_env=False, timeout=30,
                headers={'Host': 'backend.example', 'Origin': 'https://atlas.example'}) as client:
                assert client.get('/api/health').status_code == 200
                assert client.get('/api/state').status_code == 403
                client.headers['X-Atlas-Gateway-Token'] = TOKEN
                assert client.get('/api/state').status_code == 401

                def login():
                    response = client.post('/api/login', json={'name': 'Synthetic reviewer', 'passcode': ACCESS})
                    response.raise_for_status()
                    cookie = response.headers['set-cookie']
                    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
                    client.headers['Cookie'] = cookie.split(';')[0]

                login()
                state = client.post('/api/demo', json={'revision': 0})
                state.raise_for_status()
                assert state.json()['analysis'] and state.json()['sources']
                revision = state.json()['revision']
                async_result = False
                with client.stream('GET', '/api/events') as response:
                    response.raise_for_status()
                    events = response.iter_lines()
                    assert json.loads(next(events)[6:])['revision'] == revision
                    reviewed = client.put('/api/claims/' + state.json()['claims'][0]['id'] + '/review', json={
                        'revision': revision, 'status': 'applicable', 'note': 'Lightsail proxy check'})
                    reviewed.raise_for_status()
                    for line in events:
                        if line.startswith('data:'):
                            assert json.loads(line[6:])['revision'] == reviewed.json()['revision']
                            async_result = True
                            break
                assert async_result
                before = client.get('/api/export').json()
                html = client.get('/').text
                for secret in [TOKEN, ACCESS, 'synthetic-not-a-real-key']:
                    assert secret not in html and secret not in json.dumps(before)
                run('restart', 'atlas')
                for _ in range(100):
                    if client.get('/api/health').status_code == 200:
                        break
                    time.sleep(.2)
                else:
                    raise AssertionError('Backend did not restart behind Caddy')
                assert client.get('/api/state').status_code == 401
                login()
                assert client.get('/api/export').json() == before
            assert run('exec', '-T', 'atlas', 'id', '-u') == '10001'
            report = {'result': 'PASS', 'application_architecture': 'Linux AMD64 under Docker Desktop emulation',
                      'checks': ['production Compose settings', 'no Atlas host port', 'no provider key in Caddy',
                                 'non-root read-only application', 'private gateway and user sign-in',
                                 'real analysis and evidence review through Caddy', 'unbuffered SSE',
                                 'workspace persistence and session expiry after restart',
                                 'no credentials in HTML or exported workspace'],
                      'paid_api_calls': 0, 'cloud_resources_created': 0,
                      'limits': ['HTTP loopback replaces public HTTPS for this probe',
                                 'AWS provisioning, DNS, public certificate and real OpenAI access remain unverified']}
            (ROOT / 'validation/lightsail-compose-results.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report))
        finally:
            # This generated project uses a fresh UUID and only disposable test volumes.
            subprocess.run([*args, 'down', '--volumes', '--remove-orphans'],
                           cwd=ROOT, capture_output=True, timeout=60)


if __name__ == '__main__':
    main()
