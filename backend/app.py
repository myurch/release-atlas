"""Local shared-workspace API. Run one worker; remote access needs HTTPS."""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .models import MAX_REVISION, Answer, Graph, Review, Source, SourceInput, Strict, Usage, Workspace, digest, now
from .nlp import analyze, retrieve, source_digest
from .providers import ProviderConfig, ProviderError, embed, generate
from .store import Conflict, Store
from .assistant import AssistantRequest, assist, assistant_context
from .source_actions import add_source as apply_add_source, delete_source as apply_delete_source
from .input_validation import json_object
from .readme import ReadmeError, fetch_readme
from .demo_documents import load_demo_documents

ROOT = Path(__file__).resolve().parents[1]


class Login(Strict):
    name: str = Field(min_length=1, max_length=60)
    passcode: str = Field(min_length=1, max_length=200)


class Revision(Strict):
    revision: int = Field(ge=0, le=MAX_REVISION-1, strict=True)


class NewWorkspace(Revision):
    title: str = Field(min_length=1, max_length=160)
    workspace: Workspace | None = None


class SwitchWorkspace(Revision):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')


class AddSource(Revision):
    source: SourceInput


class FetchReadme(Revision):
    url: str = Field(min_length=1, max_length=1000)


class ConfirmSourceAction(Revision):
    token: str = Field(min_length=32, max_length=100)
    source_ids: list[Annotated[str, Field(pattern=r'^s-[a-f0-9]{20}$')]] | None = Field(default=None, max_length=30)


class Profile(Revision):
    usage: list[Usage] = Field(max_length=40)


class ReviewInput(Revision):
    status: str = Field(pattern=r'^(applicable|not-applicable|needs-investigation)$')
    note: str = Field(default='', max_length=2000)


class Query(Revision):
    question: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default='graph', pattern=r'^(lexical|vector|graph)$')
    use_ai: bool = False


class Import(Revision):
    workspace: Workspace


class Feed(Revision):
    repository: str = Field(pattern=r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$', max_length=160)
    rights: str = Field(min_length=3, max_length=300)


class Guard:
    """Enforce host, origin and streamed request limits before JSON parsing."""
    def __init__(self, app, origins, gateway_token=""):
        self.app = app
        self.gateway_token = gateway_token
        self.origins = origins
        self.hosts = {urlsplit(x).netloc for x in origins}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        health_probe = scope['method'] == 'GET' and scope['path'] == '/api/health'
        if self.gateway_token and not health_probe:
            tokens = [value for name, value in scope['headers'] if name == b'x-atlas-gateway-token']
            expected = self.gateway_token.encode('ascii')
            if len(tokens) != 1 or not secrets.compare_digest(tokens[0], expected):
                return await JSONResponse({'detail':'Site gateway authentication required'}, status_code=403)(scope, receive, send)
        if headers.get(b'host', b'').decode() not in self.hosts:
            return await JSONResponse({'detail':'Host is not allowed'}, status_code=400)(scope, receive, send)
        if scope['method'] not in ('GET','HEAD','OPTIONS'):
            if headers.get(b'origin', b'').decode() not in self.origins:
                return await JSONResponse({'detail':'Origin is not allowed'}, status_code=403)(scope, receive, send)
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > 2_000_000:
                    return await JSONResponse({'detail':'Request exceeds 2 MB'},status_code=413)(scope, receive, send)
                if not message.get('more_body'):
                    break
            if body:
                try:
                    json_object(body)
                except ValueError:
                    return await JSONResponse({'detail':'Invalid or ambiguous JSON input'},status_code=422)(scope, receive, send)
            sent = False

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type':'http.request','body':bytes(body),'more_body':False}
                return await receive()

            await self.app(scope, replay, send)
        else:
            await self.app(scope, receive, send)


def create_app(data_dir: Path | None = None, passcode: str | None = None, origins: list[str] | None = None, provider: ProviderConfig | None = None, auth_enabled: bool | None = None):
    data_dir = data_dir or Path(os.getenv('ATLAS_DATA_DIR', ROOT/'.atlas'))
    data_dir.mkdir(parents=True, exist_ok=True)
    if auth_enabled is None:
        auth_setting = os.getenv('ATLAS_AUTH_ENABLED', '0')
        if auth_setting not in ('0', '1'):
            raise ValueError('ATLAS_AUTH_ENABLED must be 0 or 1')
        auth_enabled = auth_setting == '1'
    public_setting = os.getenv('ATLAS_PUBLIC_ACCESS', '0')
    if public_setting not in ('0', '1'):
        raise ValueError('ATLAS_PUBLIC_ACCESS must be 0 or 1')
    public_access = public_setting == '1'
    gateway_token = os.getenv('ATLAS_GATEWAY_TOKEN', '')
    if gateway_token:
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,200}', gateway_token):
            raise ValueError('ATLAS_GATEWAY_TOKEN must contain 32 to 200 URL-safe characters')
        if (not auth_enabled and not public_access) or os.getenv('ATLAS_COOKIE_SECURE') != '1':
            raise ValueError('Hosted mode requires secure cookies and authentication or explicit public access')
    code_path = data_dir/'access-code'
    if auth_enabled and passcode is None:
        passcode = os.getenv('ATLAS_ACCESS_CODE')
        if not passcode:
            if not code_path.exists():
                fd = os.open(code_path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
                with os.fdopen(fd,'w') as file:
                    file.write(secrets.token_urlsafe(24))
            passcode = code_path.read_text().strip()
    if auth_enabled and not passcode:
        raise ValueError('An access code is required')
    origins = origins or os.getenv('ATLAS_ORIGINS', 'http://127.0.0.1:8765,http://localhost:8765').split(',')
    database_path = data_dir/'workspace.sqlite3'
    first_start = not database_path.exists()
    store = Store(database_path)
    if public_access and gateway_token and first_start:
        # Initialize a fresh public deployment only. Never reset saved visitor work.
        raw = json.loads((ROOT/'data/demo-input.json').read_text())
        example = Workspace(title=raw['title'], sources=[Source.create(SourceInput(**s)) for s in raw['sources']],
                            usage=[Usage(**u) for u in raw['usage']])
        store.save(analyze(example), 0, 'Public reviewer', 'Initialized synthetic Harbor example')
    provider = provider or ProviderConfig.environment()
    embedding = ProviderConfig.environment('ATLAS_EMBED') if os.getenv('ATLAS_EMBED_MODEL') else None
    sessions: dict[str, tuple[str,float]] = {}
    failures: dict[str,list[float]] = {}
    listeners: set[asyncio.Queue] = set()
    busy = asyncio.Lock()
    readme_busy = asyncio.Lock()
    source_proposals = {}
    app = FastAPI(title='Release Atlas', version='0.1.0', docs_url=None, redoc_url=None)
    app.add_middleware(Guard, origins=origins, gateway_token=gateway_token)
    app.state.store, app.state.listeners = store, listeners
    app.state.auth_enabled = auth_enabled

    def actor(request: Request):
        if not auth_enabled:
            return 'Public reviewer' if public_access and gateway_token else 'Local reviewer'
        key = request.cookies.get('atlas_session', '')
        identity = sessions.get(key)
        if not identity or identity[1] < time.time():
            sessions.pop(key, None)
            raise HTTPException(401, 'Sign in to the shared workspace')
        return identity[0]

    def current(revision: int):
        state = store.read()
        if state.revision != revision:
            raise HTTPException(409, 'Workspace changed. Reload and retry; your input has been kept.')
        return state

    def publish(state, expected, user, action):
        saved = store.save(state, expected, user, action)
        return notify(saved)

    def notify(saved):
        for queue in tuple(listeners):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(saved.revision)
        return saved

    @app.exception_handler(Conflict)
    async def conflict_handler(_, exc):
        return JSONResponse({'detail':str(exc)},status_code=409)

    @app.exception_handler(ProviderError)
    async def provider_handler(_, exc):
        return JSONResponse({'detail':str(exc)},status_code=502)

    @app.get('/')
    async def index():
        path = ROOT/'dist/release-atlas.html'
        if not path.exists():
            raise HTTPException(503, 'Build the frontend with npm run build')
        return FileResponse(path, headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})

    @app.get('/api/health')
    async def health():
        return {'status':'ok','version':'0.1.0'}

    @app.post('/api/login')
    async def login(data: Login, request: Request, response: Response):
        if not auth_enabled:
            raise HTTPException(404, 'Sign-in is disabled')
        ip = request.client.host if request.client else 'unknown'
        attempts = [t for t in failures.get(ip, []) if time.monotonic()-t < 60]
        failures[ip] = attempts
        if len(attempts) >= 10:
            raise HTTPException(429,'Too many attempts. Wait a minute.')
        if not secrets.compare_digest(data.passcode, passcode):
            attempts.append(time.monotonic())
            raise HTTPException(401,'Incorrect access code')
        if not data.name.strip():
            raise HTTPException(422,'Enter a display name')
        for key in [k for k,v in sessions.items() if v[1] < time.time()]:
            sessions.pop(key, None)
        if len(sessions) >= 100:
            raise HTTPException(429,'Session limit reached')
        token = secrets.token_urlsafe(32)
        sessions[token] = (data.name.strip(),time.time()+12*3600)
        response.set_cookie('atlas_session',token,httponly=True,samesite='strict',secure=os.getenv('ATLAS_COOKIE_SECURE')=='1',max_age=43200)
        return {'name':data.name.strip()}

    @app.post('/api/logout')
    async def logout(request: Request, response: Response):
        sessions.pop(request.cookies.get('atlas_session',''),None)
        response.delete_cookie('atlas_session', httponly=True, samesite='strict',
                               secure=os.getenv('ATLAS_COOKIE_SECURE') == '1')
        return {'ok':True}

    @app.get('/api/state')
    async def state(request: Request):
        user = actor(request)
        return {**store.snapshot(),'user':user,'auth_enabled':auth_enabled,'provider':{'kind':provider.kind,'model':provider.model,'embedding':embedding.model if embedding else 'local-lsa-v1'}}

    @app.post('/api/workspaces')
    async def new_workspace(data: NewWorkspace, request: Request):
        user = actor(request)
        if not data.title.strip():
            raise HTTPException(422,'Enter a workspace name')
        state = data.workspace.model_copy(deep=True) if data.workspace else Workspace()
        state.title = data.title.strip()
        try:
            return notify(store.create(state,data.revision,user,imported=data.workspace is not None))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc

    @app.post('/api/workspaces/switch')
    async def switch_workspace(data: SwitchWorkspace, request: Request):
        user = actor(request)
        try:
            return notify(store.switch(data.id,data.revision,user))
        except LookupError as exc:
            raise HTTPException(404,str(exc)) from exc

    @app.get('/api/export')
    async def export(request: Request):
        actor(request)
        return JSONResponse(store.read().model_dump(), headers={'Content-Disposition':'attachment; filename="release-atlas-review.json"','Cache-Control':'no-store'})

    @app.get('/api/events')
    async def events(request: Request):
        actor(request)
        if len(listeners) >= 40:
            raise HTTPException(429,'Too many live connections')
        queue = asyncio.Queue(maxsize=1)
        listeners.add(queue)

        async def stream():
            try:
                yield 'data: '+json.dumps({'revision':store.read().revision})+'\n\n'
                while not await request.is_disconnected():
                    try:
                        revision = await asyncio.wait_for(queue.get(),timeout=10)
                        if revision is None:
                            break
                        actor(request)
                        yield 'data: '+json.dumps({'revision':revision})+'\n\n'
                    except asyncio.TimeoutError:
                        actor(request)
                        yield ': keepalive\n\n'
            except HTTPException:
                yield 'event: expired\ndata: {}\n\n'
            finally:
                listeners.discard(queue)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request, exc):
        # Never echo untrusted input, secrets or malformed Unicode in errors.
        return JSONResponse({'detail':'Invalid request fields or unsupported limits'},status_code=422)

    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail':'Workspace exceeds supported limits or has inconsistent content; no changes saved'},status_code=422)

    @app.post('/api/sources/readme')
    async def readme_preview(data: FetchReadme, request: Request):
        user = actor(request)
        current(data.revision)
        if readme_busy.locked():
            raise HTTPException(409,'A README is already being fetched. Wait for it to finish, then try again.')
        try:
            async with readme_busy:
                result = await fetch_readme(data.url)
        except ReadmeError as exc:
            raise HTTPException(exc.status,str(exc)) from exc
        if actor(request) != user:
            raise HTTPException(401,'Session changed. Fetch the README again.')
        current(data.revision)
        return {'revision':data.revision,**result.model_dump()}

    @app.post('/api/sources/demo-documents')
    async def import_demo_documents(data: Revision, request: Request):
        user = actor(request)
        current(data.revision)
        try:
            results = await run_in_threadpool(load_demo_documents)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(503, 'Bundled demo documentation is missing or invalid. Restore the data/demo-documents files and restart Atlas. No sources were saved.') from exc
        if actor(request) != user:
            raise HTTPException(401, 'Session changed. No demo sources were saved.')
        state = current(data.revision)
        imported, skipped = [], []
        for repository, source in results:
            if any(existing.id == source.id for existing in state.sources):
                skipped.append(repository)
            else:
                apply_add_source(state, SourceInput(**source.model_dump(exclude={'id', 'sha256'})))
                imported.append(repository)
        if imported:
            state = publish(state, data.revision, user, 'Imported synthetic demo documents: '+', '.join(imported))
        return {'workspace': state, 'imported': imported, 'skipped': skipped, 'failed': []}

    @app.post('/api/sources')
    async def add_source(data: AddSource, request: Request):
        user = actor(request)
        state = current(data.revision)
        try:
            new = apply_add_source(state, data.source)
        except ValueError as exc:
            if any(s.id == Source.create(data.source).id for s in current(data.revision).sources):
                raise HTTPException(409,'This version and source content already exist') from exc
            raise HTTPException(422,'Workspace source limit exceeded') from exc
        return publish(state,data.revision,user,'Added source: '+new.title)

    @app.delete('/api/sources/{source_id}')
    async def delete_source(source_id: str, data: Revision, request: Request):
        user = actor(request)
        state = current(data.revision)
        try:
            source = apply_delete_source(state, source_id)
        except ValueError as exc:
            raise HTTPException(404, 'Source not found') from exc
        return publish(state, data.revision, user, 'Deleted source: '+source.title)

    @app.put('/api/profile')
    async def profile(data: Profile, request: Request):
        user = actor(request)
        state = current(data.revision)
        state.usage = data.usage
        state.analysis = None
        return publish(state,data.revision,user,'Updated usage profile')

    @app.post('/api/analyze')
    async def run_analysis(data: Revision, request: Request):
        user = actor(request)
        state = current(data.revision)
        if busy.locked():
            raise HTTPException(409,'Another analysis is running. Retry shortly.')
        async with busy:
            try:
                result = await run_in_threadpool(analyze,state)
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from exc
            return publish(result,data.revision,user,'Analyzed source snapshots')

    @app.post('/api/demo')
    async def load_demo(data: Revision, request: Request):
        user = actor(request)
        state = current(data.revision)
        if state.sources:
            raise HTTPException(409,'Demo only loads into an empty workspace. Export current work before importing another snapshot.')
        raw = json.loads((ROOT/'data/demo-input.json').read_text())
        result = Workspace(title=raw['title'],sources=[Source.create(SourceInput(**s)) for s in raw['sources']],usage=[Usage(**u) for u in raw['usage']])
        if busy.locked():
            raise HTTPException(409,'Another analysis is running. Retry shortly.')
        async with busy:
            result = await run_in_threadpool(analyze,result)
            return publish(result,data.revision,user,'Loaded synthetic Harbor demo')

    @app.post('/api/import')
    async def import_workspace(data: Import, request: Request):
        user = actor(request)
        current(data.revision)
        return publish(data.workspace,data.revision,user,'Imported saved analysis; embedded review names are unverified provenance')

    @app.put('/api/claims/{claim_id}/review')
    async def review(claim_id: str, data: ReviewInput, request: Request):
        user = actor(request)
        state = current(data.revision)
        if not state.analysis or source_digest(state) != state.analysis.source_digest:
            raise HTTPException(409,'Sources or usage changed. Analyze before reviewing.')
        claim = next((c for c in state.claims if c.id==claim_id),None)
        if claim is None:
            raise HTTPException(404,'Claim not found')
        claim.review = Review(status=data.status,note=data.note,by=user,at=now())
        return publish(state,data.revision,user,'Reviewed '+claim_id+': '+data.status)

    @app.post('/api/assistant')
    async def assistant_chat(data: AssistantRequest, request: Request):
        user = actor(request)
        state = current(data.revision)
        if not data.message.strip():
            raise HTTPException(422, 'Enter a question for the assistant')
        if data.selected_claim and not any(c.id == data.selected_claim for c in state.claims):
            raise HTTPException(422, 'Selected evidence is no longer available')
        if data.selected_source and not any(s.id == data.selected_source for s in state.sources):
            raise HTTPException(422, 'Selected source is no longer available')
        if busy.locked():
            raise HTTPException(409, 'Another analysis or model request is running. Try again shortly.')
        def finish(answer):
            if actor(request) != user:
                raise HTTPException(401, 'Session changed. Send your question again.')
            current(data.revision)
            result = {'revision': data.revision, **answer.model_dump()}
            prepared = getattr(answer, 'source_action', None)
            if prepared is not None:
                # Tokens never enter the model context. Bound memory, lifetime, revision and session.
                for token, entry in list(source_proposals.items()):
                    if entry['expires'] <= time.monotonic():
                        del source_proposals[token]
                if len(source_proposals) >= 128:
                    del source_proposals[next(iter(source_proposals))]
                token = secrets.token_urlsafe(32)
                source_proposals[token] = {'action': prepared.model_copy(deep=True), 'user': user,
                    'session': request.cookies.get('atlas_session', ''), 'revision': data.revision,
                    'expires': time.monotonic()+600}
                result['source_action'] = {**prepared.model_dump(), 'token': token, 'revision': data.revision}
            return result

        if data.page == 'Graph' and 'application/x-ndjson' in request.headers.get('accept',''):
            async def stream_answer():
                def frame(kind, **value):
                    return json.dumps({'type':kind, **value},ensure_ascii=False)+'\n'
                try:
                    # Recheck at generator entry: another request may have taken
                    # the lock between response creation and body iteration.
                    if busy.locked():
                        raise HTTPException(409,'Another analysis or model request is running. Try again shortly.')
                    async with busy:
                        context = await run_in_threadpool(assistant_context,state,data)
                        if actor(request) != user:
                            raise HTTPException(401,'Session changed. Send your question again.')
                        current(data.revision)
                        yield frame('retrieval',revision=data.revision,retrieval=context['retrieval'])
                        answer = await assist(provider,state,data,context=context)
                        yield frame('answer',data=finish(answer))
                except HTTPException as exc:
                    yield frame('error',status=exc.status_code,detail=exc.detail)
                except ProviderError as exc:
                    yield frame('error',status=502,detail=str(exc))
                except Exception:
                    yield frame('error',status=502,detail='The assistant could not answer. Try again or use App guide.')
            return StreamingResponse(stream_answer(),media_type='application/x-ndjson',
                headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
        async with busy:
            return finish(await assist(provider,state,data))

    @app.post('/api/assistant/source-action')
    async def confirm_source_action(data: ConfirmSourceAction, request: Request):
        user = actor(request)
        state = current(data.revision)
        entry = source_proposals.get(data.token)
        if (entry is None or entry['expires'] <= time.monotonic() or entry['user'] != user
                or entry['session'] != request.cookies.get('atlas_session', '') or entry['revision'] != data.revision):
            raise HTTPException(409, 'Source proposal expired or belongs to another session. Ask Atlas again.')
        plan = entry['action']
        expected_ids = [item.source_id for item in plan.items]
        if (len(expected_ids) > 1 or data.source_ids is not None) and data.source_ids != expected_ids:
            raise HTTPException(409, 'Confirm the complete current source list. Refresh the page to load the batch preview.')
        try:
            for item in plan.items:
                if plan.action == 'add_source':
                    apply_add_source(state, item.source)
                else:
                    apply_delete_source(state, item.source_id)
            verb = 'Added' if plan.action == 'add_source' else 'Deleted'
            action = (verb+' source: '+plan.source.title if len(plan.items) == 1
                      else f'{verb} {len(plan.items)} sources through chat')
        except ValueError as exc:
            raise HTTPException(422, 'Source action is no longer valid. Ask Atlas again.') from exc
        saved = publish(state, data.revision, user, action)
        del source_proposals[data.token]
        return {'revision': saved.revision, 'action': plan.action, 'source_id': plan.source_id,
                'source_ids':[item.source_id for item in plan.items],
                'message': action+'. Analyze sources to refresh findings.'}

    @app.post('/api/query')
    async def query(data: Query, request: Request):
        user = actor(request)
        state = current(data.revision)
        if not data.question.strip():
            raise HTTPException(422,'Enter a question')
        if not state.analysis or source_digest(state) != state.analysis.source_digest:
            raise HTTPException(409,'Analyze current sources and usage before asking questions')
        if busy.locked():
            raise HTTPException(409,'Another analysis is running. Retry shortly.')
        async with busy:
            vectors = None
            if embedding and data.mode != 'lexical':
                vectors = await embed(embedding,[c.quote for c in state.claims]+[data.question])
            evidence = await run_in_threadpool(retrieve,state,data.question,data.mode,6,vectors)
            method = data.mode+' retrieval'
            if vectors:
                method += ' ('+embedding.kind+'/'+embedding.model+', '+str(len(vectors[0]))+' dimensions)'
            if data.use_ai and evidence:
                generated = await generate(provider,data.question,evidence)
                answer, citations, uncertainty = generated.answer, generated.citations, generated.uncertainty
                method += ' + '+provider.kind+'/'+provider.model
            else:
                answer = '\n\n'.join(row['claim']['quote'] for row in evidence) if evidence else 'No matching evidence was found in this workspace.'
                citations = [row['claim']['id'] for row in evidence]
                uncertainty = 'Retrieved passages only. Applicability and contradictions require human review.' if evidence else 'No conclusion about upgrade safety can be drawn.'
            entry = Answer(id='a-'+secrets.token_hex(8),question=data.question,answer=answer,citations=citations,uncertainty=uncertainty,method=method,at=now())
            state.answers = (state.answers+[entry])[-30:]
            saved = publish(state,data.revision,user,'Asked an evidence question')
            return {'workspace':saved.model_dump(),'evidence':evidence,'answer':entry.model_dump(),'embedding':embedding.model if vectors else 'local-lsa-v1'}

    @app.post('/api/feeds/github')
    async def feed(data: Feed, request: Request):
        user = actor(request)
        state = current(data.revision)
        url = 'https://api.github.com/repos/'+data.repository+'/releases?per_page=3'
        try:
            async with asyncio.timeout(20):
                async with httpx.AsyncClient(timeout=15,trust_env=False,follow_redirects=False) as client:
                    async with client.stream('GET',url,headers={'Accept':'application/vnd.github+json','User-Agent':'Release-Atlas/0.1'}) as response:
                        if response.status_code != 200:
                            raise HTTPException(502,f'GitHub returned HTTP {response.status_code}; check the repository or rate limit')
                        body=bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body)>250000:
                                raise HTTPException(422,'Release feed exceeds the allowed size')
            releases = json.loads(body)
            if not isinstance(releases,list):
                raise ValueError('Unexpected feed')
            count = 0
            for release in releases:
                if release.get('draft') or not str(release.get('body') or '').strip():
                    continue
                source = Source.create(SourceInput(title=str(release.get('name') or release['tag_name'])[:160],version=release['tag_name'],text=release['body'],url=release['html_url'],license=data.rights))
                if not any(s.id==source.id for s in state.sources):
                    state.sources.append(source)
                    state.analysis = None
                    count+=1
            if not count:
                raise HTTPException(422,'No new nonempty releases found')
            Workspace.model_validate(state.model_dump())
        except (httpx.HTTPError, TimeoutError) as exc:
            raise HTTPException(502,'GitHub feed unavailable; no changes saved') from exc
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise HTTPException(422,'Feed content or workspace exceeds supported limits; no changes saved') from exc
        return publish(state,data.revision,user,f'Imported {count} GitHub release snapshots')

    return app
