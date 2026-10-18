"""Public README fetching, actionable failures and a read-only guarded draft endpoint."""
import asyncio
import base64
import hashlib
import importlib
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.models import Workspace
from backend.readme import ReadmeDraft, ReadmeError, fetch_readme, repository_from_url

URL = 'https://github.com/example/project'
COMMIT = 'a'*40
ORIGIN = {'Origin':'http://testserver'}
TEXT = '# Synthetic README\r\n🧭 Café\n\tSELECT * FROM workspace;\n<script>inert()</script>\n'


def document(raw=TEXT.encode(),**changes):
    blob = b'blob '+str(len(raw)).encode()+b'\0'+raw
    return {'type':'file','encoding':'base64','path':'README.md','size':len(raw),
            'sha':hashlib.sha1(blob).hexdigest(),'content':base64.b64encode(raw).decode(),
            'download_url':'http://169.254.169.254/must-never-be-requested',**changes}


def wire(*,repo=None,commit=None,readme=None,fail_stage=None,status=200,exception=None,body=None,requests=None):
    def handle(request):
        if requests is not None:
            requests.append(request)
        assert request.method == 'GET' and request.url.host == 'api.github.com'
        assert not request.headers.get('Authorization') and not request.headers.get('Cookie')
        stage = 'readme' if request.url.path.endswith('/readme') else 'commit' if '/commits/' in request.url.path else 'repo'
        if stage == fail_stage:
            if exception:
                raise exception
            return httpx.Response(status,content=body) if body is not None else httpx.Response(status,json={'message':'UNTRUSTED_ERROR'})
        data = {'repo':repo if repo is not None else {'private':False,'visibility':'public','default_branch':'main'},
                'commit':commit if commit is not None else {'sha':COMMIT},
                'readme':readme if readme is not None else document()}[stage]
        return httpx.Response(200,json=data)
    return httpx.MockTransport(handle)


@pytest.mark.parametrize('url',[URL,URL+'/',URL+'.git','https://GitHub.com/example/project'])
def test_public_repository_urls_are_normalized(url):
    assert repository_from_url(url) == 'example/project'


@pytest.mark.parametrize('url',[
    'http://github.com/example/project','https://evil.invalid/example/project',
    'https://github.com.evil.invalid/example/project','https://github.com@evil.invalid/example/project',
    'https://user:secret@github.com/example/project','https://github.com:443/example/project',
    'https://127.0.0.1/example/project','https://169.254.169.254/latest/meta-data',
    'file:///tmp/README.md',URL+'?redirect=evil',URL+'#readme',URL+'/blob/main/README.md',
    'https://github.com/example/../secret','https://github.com/example/%2e%2e','https://github.com//example/project',
    '[repo]('+URL+')','https://github.com/example/pro ject',
])
def test_untrusted_or_unsupported_urls_are_rejected_before_network_access(url):
    with pytest.raises(ReadmeError,match='public GitHub repository URL') as error:
        repository_from_url(url)
    assert error.value.status == 422


@pytest.mark.asyncio
async def test_readme_is_pinned_to_commit_and_keeps_exact_unicode_and_code(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN','PRIVATE_GITHUB_TOKEN')
    monkeypatch.setenv('OPENAI_API_KEY','PRIVATE_PROVIDER_TOKEN')
    monkeypatch.setenv('HTTP_PROXY','http://untrusted.invalid')
    calls = []
    result = await fetch_readme(URL,wire(requests=calls))
    assert len(calls) == 3
    assert [request.url.path for request in calls] == ['/repos/example/project','/repos/example/project/commits/main','/repos/example/project/readme']
    assert calls[-1].url.params['ref'] == COMMIT
    assert result.source.text == TEXT and result.commit == COMMIT
    assert result.source.version == 'commit:'+COMMIT
    assert result.source.url == URL+'/blob/'+COMMIT+'/README.md'
    assert result.source.title == 'example/project README'
    assert 'verify redistribution rights' in result.source.license


@pytest.mark.asyncio
async def test_default_branch_slashes_are_encoded_and_non_root_readme_has_pinned_origin():
    calls = []
    result = await fetch_readme(URL,wire(repo={'private':False,'default_branch':'release/next'},
        readme=document(path='.github/README.md'),requests=calls))
    assert b'/commits/release%2Fnext' in calls[1].url.raw_path
    assert result.path == '.github/README.md' and result.source.url.endswith('/.github/README.md')


@pytest.mark.parametrize('stage,status,expected,message',[
    ('repo',404,404,'Public repository not found'),
    ('readme',404,404,'no README available'),
    ('commit',404,404,'no readable default-branch commit'),
    ('commit',409,404,'no committed README'),
    ('repo',403,503,'rate limit'),('readme',429,503,'rate limit'),
    ('repo',301,422,'redirected'),('readme',302,422,'redirected'),
    ('repo',500,502,'temporarily unavailable'),('readme',503,502,'temporarily unavailable'),
    ('readme',422,502,'could not return'),
])
@pytest.mark.asyncio
async def test_github_failures_have_actionable_sanitized_messages(stage,status,expected,message):
    with pytest.raises(ReadmeError,match=message) as error:
        await fetch_readme(URL,wire(fail_stage=stage,status=status))
    assert error.value.status == expected and 'UNTRUSTED_ERROR' not in str(error.value)


@pytest.mark.parametrize('exception,status,message',[
    (httpx.ReadTimeout('UNTRUSTED_ERROR'),504,'did not respond in time'),
    (httpx.ConnectError('UNTRUSTED_ERROR'),502,'Could not connect'),
])
@pytest.mark.asyncio
async def test_unresponsive_and_unreachable_api_preserve_clear_retry_messages(exception,status,message):
    with pytest.raises(ReadmeError,match=message) as error:
        await fetch_readme(URL,wire(fail_stage='repo',exception=exception))
    assert error.value.status == status and 'UNTRUSTED_ERROR' not in str(error.value)


@pytest.mark.asyncio
async def test_one_overall_deadline_bounds_the_whole_fetch(monkeypatch):
    monkeypatch.setattr(importlib.import_module('backend.readme'),'TIMEOUT',0.01)
    async def slow(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200,json={})
    with pytest.raises(ReadmeError,match='did not respond in time'):
        await fetch_readme(URL,httpx.MockTransport(slow))


@pytest.mark.parametrize('raw,status,message',[
    (b'',422,'empty README'),(b' \n\t',422,'empty README'),
    (b'x'*12001,422,'12,000-character'),(b'\xff',502,'unreadable'),
    (b'invalid\x00content',502,'unreadable'),
])
@pytest.mark.asyncio
async def test_empty_oversized_and_unsupported_readmes_are_not_truncated(raw,status,message):
    with pytest.raises(ReadmeError,match=message) as error:
        await fetch_readme(URL,wire(readme=document(raw)))
    assert error.value.status == status


@pytest.mark.asyncio
async def test_twelve_thousand_unicode_code_points_fit_the_source_limit():
    result = await fetch_readme(URL,wire(readme=document(('🧭'*12000).encode())))
    assert result.source.text == '🧭'*12000


@pytest.mark.parametrize('changes',[
    {'type':'symlink'},{'encoding':'none'},{'size':True},{'size':1},{'size':-1},
    {'content':'%%%invalid%%%'},{'sha':'f'*40},{'sha':'wrong'},
    {'path':'../README.md'},{'path':'/README.md'},{'path':'docs/../README.md'},
    {'path':'docs\\README.md'},{'path':'other.txt'},
])
@pytest.mark.asyncio
async def test_corrupt_content_metadata_or_hashes_are_rejected(changes):
    with pytest.raises(ReadmeError,match='unreadable or invalid'):
        await fetch_readme(URL,wire(readme=document(**changes)))


@pytest.mark.parametrize('info',[
    {'private':True,'default_branch':'main'}, {'default_branch':'main'},
    {'private':False,'visibility':'private','default_branch':'main'},
])
@pytest.mark.asyncio
async def test_private_or_unproven_public_repositories_are_rejected(info):
    with pytest.raises(ReadmeError,match='Only public'):
        await fetch_readme(URL,wire(repo=info))


@pytest.mark.asyncio
async def test_empty_repository_and_invalid_responses_have_clear_failures():
    with pytest.raises(ReadmeError,match='no readable default branch'):
        await fetch_readme(URL,wire(repo={'private':False,'default_branch':''}))
    for body,message in [(b'<html>not JSON</html>','unreadable'),(b'{"private":true,"private":false}','unreadable'),(b'x'*250001,'more data')]:
        with pytest.raises(ReadmeError,match=message):
            await fetch_readme(URL,wire(fail_stage='repo',body=body))


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path,auth_enabled=True,passcode='code',origins=['http://testserver'])
    with TestClient(app) as client:
        client.post('/api/login',headers=ORIGIN,json={'name':'Reviewer','passcode':'code'})
        yield client,app


def mock_fetch(monkeypatch,transport=None):
    async def fetched(url):
        return await fetch_readme(url,transport or wire())
    monkeypatch.setattr(importlib.import_module('backend.app'),'fetch_readme',fetched)


def test_preview_does_not_save_and_source_save_uses_existing_validation(client,monkeypatch):
    client,app = client
    mock_fetch(monkeypatch)
    before = app.state.store.snapshot()
    response = client.post('/api/sources/readme',headers=ORIGIN,json={'revision':0,'url':URL})
    assert response.status_code == 200,response.text
    assert response.json()['revision'] == 0 and response.json()['source']['text'] == TEXT
    assert app.state.store.snapshot() == before
    source = response.json()['source']
    source['license'] = 'Synthetic fixture; permitted for tests'
    saved = client.post('/api/sources',headers=ORIGIN,json={'revision':0,'source':source})
    assert saved.status_code == 200 and app.state.store.read().sources[0].text == TEXT
    assert app.state.store.read().audit[-1].action.startswith('Added source:')


def test_preview_requires_origin_session_revision_and_exact_fields_before_network(client,monkeypatch):
    client,app = client
    calls = []
    async def unexpected(url):
        calls.append(url)
        raise AssertionError('Unexpected outbound request')
    monkeypatch.setattr(importlib.import_module('backend.app'),'fetch_readme',unexpected)
    body = {'revision':0,'url':URL}
    assert client.post('/api/sources/readme',json=body).status_code == 403
    assert client.post('/api/sources/readme',headers=ORIGIN,json={**body,'revision':1}).status_code == 409
    for edit in [{'revision':True},{'revision':0.0},{'revision':'0'},{'url':'x'*1001},{'url':'invalid\x00'},{'headers':{'Authorization':'secret'}},{'sql':'DROP TABLE workspace'}]:
        assert client.post('/api/sources/readme',headers=ORIGIN,json={**body,**edit}).status_code == 422
    client.post('/api/logout',headers=ORIGIN)
    assert client.post('/api/sources/readme',headers=ORIGIN,json=body).status_code == 401
    assert calls == [] and app.state.store.read() == Workspace()


@pytest.mark.parametrize('status,message',[(404,'no README available'),(503,'temporarily unavailable')])
def test_upstream_api_errors_leave_database_unchanged(client,monkeypatch,status,message):
    client,app = client
    mock_fetch(monkeypatch,wire(fail_stage='readme',status=status))
    before = app.state.store.snapshot()
    response = client.post('/api/sources/readme',headers=ORIGIN,json={'revision':0,'url':URL})
    assert message in response.json()['detail'] and response.status_code in (404,502)
    assert app.state.store.snapshot() == before


@pytest.mark.parametrize('switch',[False,True])
def test_stale_preview_never_reaches_changed_or_other_workspace(client,monkeypatch,switch):
    client,app = client
    async def changed(url):
        if switch:
            app.state.store.create(Workspace(title='Other'),0,'Peer')
        else:
            app.state.store.save(Workspace(title='Changed'),0,'Peer','Edit')
        return await fetch_readme(url,wire())
    monkeypatch.setattr(importlib.import_module('backend.app'),'fetch_readme',changed)
    assert client.post('/api/sources/readme',headers=ORIGIN,json={'revision':0,'url':URL}).status_code == 409
    assert app.state.store.read().sources == [] and app.state.store.read().revision == 1


def test_session_expiry_during_fetch_discards_preview(client,monkeypatch):
    client,app = client
    original = time.time
    async def expired(url):
        result = await fetch_readme(url,wire())
        monkeypatch.setattr(time,'time',lambda: original()+13*3600)
        return result
    monkeypatch.setattr(importlib.import_module('backend.app'),'fetch_readme',expired)
    assert client.post('/api/sources/readme',headers=ORIGIN,json={'revision':0,'url':URL}).status_code == 401
    assert app.state.store.read() == Workspace()


@pytest.mark.asyncio
async def test_only_one_readme_fetch_is_allowed_at_once(tmp_path,monkeypatch):
    app = create_app(tmp_path,auth_enabled=False,origins=['http://testserver'])
    started,release = asyncio.Event(),asyncio.Event()
    async def held(url):
        started.set()
        await release.wait()
        return await fetch_readme(url,wire())
    monkeypatch.setattr(importlib.import_module('backend.app'),'fetch_readme',held)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',headers=ORIGIN) as client:
        body = {'revision':0,'url':URL}
        first = asyncio.create_task(client.post('/api/sources/readme',json=body))
        await started.wait()
        second = await client.post('/api/sources/readme',json=body)
        assert second.status_code == 409 and 'already being fetched' in second.json()['detail']
        release.set()
        assert (await first).status_code == 200
    assert app.state.store.read() == Workspace()
