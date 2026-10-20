"""Exercise the Site gateway and Python service over HTTP using synthetic data only.

Usage: .venv/bin/python tools/hosted_probe.py /path/to/site/server/gateway.mjs
The injected transport substitutes loopback HTTP for the fixed test HTTPS origin.
This checks the actual proxy function, not cloud TLS or a real model account.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
import uvicorn
from backend import app as module, semantic
from backend.assistant import AssistantReply
from backend.providers import ProviderConfig

TOKEN = 'synthetic-gateway-0123456789abcdef0123456789'
ACCESS = 'synthetic-access-0123456789abcdef0123456789'
SITE = 'https://atlas.example'
BACKEND = 'https://backend.example'

BRIDGE = r'''
import http from 'node:http';
import { Readable } from 'node:stream';
const { gateway } = await import(process.env.ATLAS_PROBE_GATEWAY);
const environment = {
  ATLAS_BACKEND_ORIGIN: 'https://backend.example',
  ATLAS_GATEWAY_TOKEN: process.env.ATLAS_PROBE_TOKEN,
};
const server = http.createServer(async (req, res) => {
  const controller = new AbortController();
  res.on('close', () => controller.abort());
  try {
    const body = ['GET', 'HEAD'].includes(req.method) ? undefined : Readable.toWeb(req);
    const request = new Request('https://atlas.example' + req.url, {
      method: req.method, headers: req.headers, body, duplex: 'half', signal: controller.signal,
    });
    const result = await gateway(request, environment, (url, options) => {
      const target = new URL(url.pathname + url.search, process.env.ATLAS_PROBE_BACKEND);
      options.headers.set('Host', 'backend.example');
      return fetch(target, options);
    });
    res.writeHead(result.status, Object.fromEntries(result.headers));
    res.flushHeaders();
    if (result.body) Readable.fromWeb(result.body).on('error', () => res.destroy()).pipe(res);
    else res.end();
  } catch {
    res.writeHead(502); res.end('Test bridge failed');
  }
});
server.listen(0, '127.0.0.1', () => console.log(server.address().port));
'''


async def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        raise SystemExit('Pass the Site server/gateway.mjs path as the only argument.')
    release = asyncio.Event()
    model_calls = []

    async def generate(config, state, data, *, context):
        model_calls.append(data.message)
        await release.wait()
        return AssistantReply(answer='Synthetic held model response.', retrieval=context['retrieval'])

    with tempfile.TemporaryDirectory(prefix='atlas-hosted-probe-') as directory, \
            patch.dict(os.environ, {'ATLAS_GATEWAY_TOKEN': TOKEN, 'ATLAS_COOKIE_SECURE': '1'}):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        app = module.create_app(Path(directory), passcode=ACCESS, auth_enabled=True,
                                    origins=[SITE, BACKEND, origin],
                                    provider=ProviderConfig(key='synthetic-not-a-real-key'))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=1))
        with patch.object(module, 'assist', generate), patch.object(semantic, 'configuration',
                return_value=(None, 'Statistical test encoder.')):
            task = asyncio.create_task(server.serve(sockets=[listener]))
            bridge = None
            try:
                for _ in range(100):
                    if server.started:
                        break
                    await asyncio.sleep(.02)
                assert server.started
                bridge = await asyncio.create_subprocess_exec('node', '--input-type=module', '-e', BRIDGE,
                    env={**os.environ, 'ATLAS_PROBE_GATEWAY': Path(sys.argv[1]).resolve().as_uri(),
                         'ATLAS_PROBE_BACKEND': origin, 'ATLAS_PROBE_TOKEN': TOKEN},
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                port = int((await asyncio.wait_for(bridge.stdout.readline(), 5)).decode().strip())
                async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', timeout=10,
                                             trust_env=False, headers={'Origin': SITE}) as client:
                    async with httpx.AsyncClient(trust_env=False) as direct:
                        assert (await direct.get(origin + '/api/state')).status_code == 403
                        assert (await direct.get(origin + '/api/health')).status_code == 200
                    assert (await client.get('/api/state')).status_code == 401
                    assert (await client.post('/api/assistant', json={'revision': 0, 'page': 'Graph',
                        'message': 'This must not reach a model.'})).status_code == 401
                    assert model_calls == []
                    login = await client.post('/api/login', json={'name': 'Synthetic reviewer', 'passcode': ACCESS})
                    login.raise_for_status()
                    cookie = login.headers['set-cookie']
                    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
                    # This test uses plain loopback HTTP, so send the secure cookie explicitly.
                    client.headers['Cookie'] = cookie.split(';')[0]
                    page = await client.get('/')
                    assert page.status_code == 200 and 'Release Atlas' in page.text
                    for secret in (TOKEN, ACCESS, 'synthetic-not-a-real-key'):
                        assert secret not in page.text
                    state = (await client.post('/api/demo', json={'revision': 0})).json()
                    assert state['sources'] and state['analysis'] and state['claims']
                    revision = state['revision']
                    async with client.stream('GET', '/api/events') as response:
                        response.raise_for_status()
                        events = response.aiter_lines()
                        assert json.loads((await anext(events))[6:])['revision'] == revision
                        reviewed = await client.put('/api/claims/' + state['claims'][0]['id'] + '/review',
                            json={'revision': revision, 'status': 'applicable', 'note': 'Gateway probe'})
                        reviewed.raise_for_status()
                        revision = reviewed.json()['revision']
                        for _ in range(10):
                            line = await asyncio.wait_for(anext(events), 5)
                            if line.startswith('data:'):
                                assert json.loads(line[6:])['revision'] == revision
                                break
                        else:
                            raise AssertionError('No streamed revision event')
                    assert (await client.put('/api/profile', json={'revision': revision - 1,
                        'usage': []})).status_code == 409
                    profile = await client.put('/api/profile', json={'revision': revision, 'usage': []})
                    profile.raise_for_status()
                    analyzed = await client.post('/api/analyze', json={'revision': profile.json()['revision']})
                    analyzed.raise_for_status()
                    revision = analyzed.json()['revision']
                    async with client.stream('POST', '/api/assistant',
                        headers={'Accept': 'application/x-ndjson'}, json={'revision': revision,
                        'page': 'Graph', 'message': 'What changed in legacy_auth?'}) as response:
                        response.raise_for_status()
                        frames = response.aiter_lines()
                        first = json.loads(await asyncio.wait_for(anext(frames), 5))
                        assert first['type'] == 'retrieval' and not release.is_set()
                        release.set()
                        final = json.loads(await asyncio.wait_for(anext(frames), 5))
                        assert final['type'] == 'answer'
                        assert final['data']['retrieval'] == first['retrieval']
                    exported = await client.get('/api/export')
                    exported.raise_for_status()
                    assert exported.json()['revision'] == revision
                    assert len(model_calls) == 1
                    logout = await client.post('/api/logout')
                    assert 'Max-Age=0' in logout.headers['set-cookie']
                    assert (await client.get('/api/state')).status_code == 401
                    stored = app.state.store.read()
                    assert stored.revision == revision and stored.sources
                report = {'result': 'PASS', 'transport': 'real loopback HTTP through the actual Site gateway',
                    'checks': ['direct backend guard', 'sign-in before model calls', 'private credentials',
                               'live HTML', 'real analysis', 'profile and review PUT', 'revision conflicts',
                               'SSE collaboration', 'retrieval-first NDJSON chat', 'export', 'secure logout'],
                    'model_generation': 'held synthetic mock', 'paid_api_calls': 0,
                    'limits': ['Cloud TLS and provider hosting are not tested',
                               'Real OpenAI access requires a provisioned backend',
                               'No existing user workspaces or secrets were read']}
                (ROOT / 'validation/hosted-gateway-results.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps(report))
            finally:
                release.set()
                if bridge is not None:
                    bridge.terminate()
                    await asyncio.wait_for(bridge.wait(), 5)
                server.should_exit = True
                await asyncio.wait_for(task, 5)
                listener.close()


if __name__ == '__main__':
    asyncio.run(main())
