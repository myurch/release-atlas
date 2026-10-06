"""Isolated real HTTP/SSE and public-feed integration check. No paid provider calls."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:18877'


async def main():
    with tempfile.TemporaryDirectory(prefix='atlas-http-') as temp:
        env = {**os.environ, 'ATLAS_DATA_DIR':temp, 'ATLAS_PORT':'18877', 'ATLAS_ORIGINS':BASE, 'ATLAS_ACCESS_CODE':'isolated-integration-fixture', 'PYTHONDONTWRITEBYTECODE':'1'}
        process = subprocess.Popen([sys.executable,'-m','backend'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            async with httpx.AsyncClient(base_url=BASE, timeout=25, trust_env=False, headers={'Origin':BASE}) as a, httpx.AsyncClient(base_url=BASE, timeout=25, trust_env=False, headers={'Origin':BASE}) as b:
                for _ in range(100):
                    try:
                        if (await a.get('/api/health')).status_code == 200: break
                    except httpx.HTTPError: pass
                    await asyncio.sleep(.1)
                else: raise RuntimeError('Isolated server did not start')
                for client, name in [(a,'Alex'), (b,'Blair')]:
                    (await client.post('/api/login',json={'name':name,'passcode':env['ATLAS_ACCESS_CODE']})).raise_for_status()
                state=(await a.post('/api/demo',json={'revision':0})).json()
                cid=state['claims'][0]['id']
                async with b.stream('GET','/api/events') as stream:
                    lines=stream.aiter_lines()
                    assert json.loads((await anext(lines))[6:])['revision']==1
                    saved=await a.put(f'/api/claims/{cid}/review',json={'revision':1,'status':'applicable','note':'HTTP probe'})
                    assert saved.status_code==200
                    while True:
                        line=await anext(lines)
                        if line.startswith('data:'): break
                    assert json.loads(line[6:])['revision']==2
                assert (await b.put(f'/api/claims/{cid}/review',json={'revision':1,'status':'not-applicable'})).status_code==409
                # A fresh stream receives the current persisted revision even after missing a change.
                async with b.stream('GET','/api/events') as stream:
                    assert json.loads((await anext(stream.aiter_lines()))[6:])['revision']==2
                snapshot=(await b.get('/api/export')).json()
                assert snapshot['claims'][0]['review']['by']=='Alex'
                imported=await b.post('/api/import',json={'revision':2,'workspace':snapshot})
                assert imported.status_code==200 and imported.json()['revision']==3
                feed=await a.post('/api/feeds/github',json={'revision':3,'repository':'tj/commander.js','rights':'Read-only integration test; check upstream rights before redistribution'})
                feed.raise_for_status()
                added=len(feed.json()['sources'])-len(snapshot['sources'])
                assert 1<=added<=3
                assert feed.json()['analysis'] is None
                original=(await a.get('/api/state')).json()
                original_id=original['active_id']
                async with b.stream('GET','/api/events') as stream:
                    lines=stream.aiter_lines()
                    assert json.loads((await anext(lines))[6:])['revision']==4
                    created=await a.post('/api/workspaces',json={'revision':4,'title':'Next upgrade'})
                    assert created.status_code==200 and created.json()['sources']==[]
                    while True:
                        line=await anext(lines)
                        if line.startswith('data:'): break
                    assert json.loads(line[6:])['revision']==5
                    assert (await b.get('/api/state')).json()['workspace']['title']=='Next upgrade'
                    assert (await b.post('/api/workspaces/switch',json={'revision':4,'id':original_id})).status_code==409
                    switched=await a.post('/api/workspaces/switch',json={'revision':5,'id':original_id})
                    assert switched.status_code==200 and switched.json()['claims']==original['workspace']['claims']
                    while True:
                        line=await anext(lines)
                        if line.startswith('data:'): break
                    assert json.loads(line[6:])['revision']==6
                assert len((await b.get('/api/state')).json()['workspaces'])==2
                report={'result':'PASS','checks':['Real HTTP login for distinct sessions','Authenticated SSE initial and changed revisions','Stale write rejected with 409','SSE reconnect receives current state','Export/import round trip preserves cited review','Actual public GitHub release feed stores bounded versioned snapshots','New empty workspace preserves existing review and notifies a second session','Switch restores saved claims with a fresh global revision and SSE notification','Stale cross-workspace selection returns 409'], 'github_source_count_added':added,'github_repository':'tj/commander.js','feed_content_distributed':False,'limits':['One loopback process; no load or WAN proxy test','Temporary workspace removed after process exit']}
                (ROOT/'validation/integration-results.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(report))
        finally:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()


asyncio.run(main())
