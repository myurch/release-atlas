import os

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.hosted import configure
from backend.providers import ProviderConfig

TOKEN = 'test-gateway-token-0123456789abcdef0123456789'
ACCESS = 'test-access-code-0123456789abcdef0123456789'
ORIGIN = 'https://atlas.example'
HEADERS = {'Origin': ORIGIN, 'X-Atlas-Gateway-Token': TOKEN}


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLAS_GATEWAY_TOKEN', TOKEN)
    monkeypatch.setenv('ATLAS_COOKIE_SECURE', '1')
    app = create_app(tmp_path, passcode=ACCESS, auth_enabled=True, origins=[ORIGIN],
                     provider=ProviderConfig(key='synthetic-provider-key'))
    with TestClient(app, base_url=ORIGIN) as client:
        yield client


def test_direct_backend_access_is_denied_but_health_stays_available(hosted):
    assert hosted.get('/api/health').status_code == 200
    for path in ['/', '/api/state', '/api/export', '/api/workspaces', '/api/events']:
        assert hosted.get(path).status_code == 403
    assert hosted.post('/api/login', json={'name': 'A', 'passcode': ACCESS},
                       headers={'Origin': ORIGIN}).status_code == 403
    assert hosted.get('/api/state', headers={'X-Atlas-Gateway-Token': 'wrong'}).status_code == 403
    assert hosted.get('/api/health', headers={'Host': 'evil.example'}).status_code == 400


def test_gateway_is_not_a_replacement_for_user_authentication(hosted):
    assert hosted.get('/api/state', headers=HEADERS).status_code == 401
    assert hosted.post('/api/demo', json={'revision': 0}, headers=HEADERS).status_code == 401
    response = hosted.post('/api/login', json={'name': 'Reviewer', 'passcode': ACCESS}, headers=HEADERS)
    assert response.status_code == 200
    cookie = response.headers['set-cookie'].lower()
    assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
    assert hosted.get('/api/state', headers=HEADERS).status_code == 200
    assert hosted.get('/api/state').status_code == 403
    saved = hosted.post('/api/demo', json={'revision': 0}, headers=HEADERS)
    assert saved.status_code == 200
    revision = saved.json()['revision']
    assert hosted.post('/api/analyze', json={'revision': revision}, headers=HEADERS).status_code == 200
    assert hosted.post('/api/demo', json={'revision': revision}, headers=HEADERS).status_code == 409
    logout = hosted.post('/api/logout', headers=HEADERS)
    assert logout.status_code == 200
    cleared = logout.headers['set-cookie'].lower()
    assert 'max-age=0' in cleared and 'secure' in cleared and 'httponly' in cleared and 'samesite=strict' in cleared
    assert hosted.get('/api/state', headers=HEADERS).status_code == 401


def test_origin_limits_and_ambiguous_gateway_headers_remain_blocked(hosted):
    assert hosted.post('/api/login', json={'name': 'A', 'passcode': ACCESS},
                       headers={'X-Atlas-Gateway-Token': TOKEN}).status_code == 403
    assert hosted.post('/api/login', json={'name': 'A', 'passcode': ACCESS},
                       headers={**HEADERS, 'Origin': 'https://evil.example'}).status_code == 403
    assert hosted.get('/api/state', headers=[('X-Atlas-Gateway-Token', TOKEN),
                                             ('X-Atlas-Gateway-Token', TOKEN)]).status_code == 403
    response = hosted.post('/api/login', content=b'x' * 2_000_001, headers=HEADERS)
    assert response.status_code == 413
    response = hosted.post('/api/login', content=b'{"name":"A","name":"B"}', headers=HEADERS)
    assert response.status_code == 422


@pytest.mark.parametrize('auth,secure,token', [(False, '1', TOKEN), (True, '0', TOKEN), (True, '1', 'short')])
def test_gateway_startup_fails_closed(tmp_path, monkeypatch, auth, secure, token):
    monkeypatch.setenv('ATLAS_GATEWAY_TOKEN', token)
    monkeypatch.setenv('ATLAS_COOKIE_SECURE', secure)
    with pytest.raises(ValueError):
        create_app(tmp_path, passcode=ACCESS, auth_enabled=auth, origins=[ORIGIN])


@pytest.fixture
def configured_env(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith('ATLAS_') or key in {'OPENAI_API_KEY', 'PORT', 'RENDER_EXTERNAL_URL'}:
            monkeypatch.delenv(key)
    for key, value in {
        'ATLAS_GATEWAY_TOKEN': TOKEN, 'ATLAS_ACCESS_CODE': ACCESS,
        'OPENAI_API_KEY': 'synthetic-provider-key', 'ATLAS_SITE_ORIGIN': ORIGIN,
        'RENDER_EXTERNAL_URL': 'https://atlas-backend.onrender.com',
        'ATLAS_DATA_DIR': str(tmp_path), 'PORT': '10000',
        # configure() writes these keys; register them so monkeypatch restores each one.
        'ATLAS_AUTH_ENABLED': '0', 'ATLAS_COOKIE_SECURE': '0', 'ATLAS_HOST': '127.0.0.1',
        'ATLAS_PORT': '8765', 'ATLAS_ORIGINS': '', 'ATLAS_LLM_KIND': '', 'ATLAS_LLM_BASE': '',
    }.items():
        monkeypatch.setenv(key, value)


def test_hosted_entrypoint_forces_auth_and_explicit_origins(configured_env, monkeypatch):
    monkeypatch.setenv('ATLAS_AUTH_ENABLED', '0')
    monkeypatch.setenv('ATLAS_COOKIE_SECURE', '0')
    configure()
    assert os.environ['ATLAS_AUTH_ENABLED'] == '1'
    assert os.environ['ATLAS_COOKIE_SECURE'] == '1'
    assert os.environ['ATLAS_PORT'] == '10000'
    assert os.environ['ATLAS_ORIGINS'] == ORIGIN + ',https://atlas-backend.onrender.com,http://127.0.0.1:10000'
    assert os.environ['ATLAS_LLM_BASE'] == 'https://api.openai.com/v1'


@pytest.mark.parametrize('key,value', [
    ('ATLAS_GATEWAY_TOKEN', ''), ('ATLAS_ACCESS_CODE', 'simple'), ('OPENAI_API_KEY', ''),
    ('ATLAS_SITE_ORIGIN', 'http://atlas.example'), ('ATLAS_SITE_ORIGIN', 'https://secret@atlas.example'),
    ('ATLAS_SITE_ORIGIN', 'https://atlas.example/path'), ('ATLAS_SITE_ORIGIN', 'https://atlas.example?x=1'),
    ('RENDER_EXTERNAL_URL', ''), ('ATLAS_DATA_DIR', 'relative'), ('ATLAS_DATA_DIR', '/'),
    ('PORT', '0'), ('PORT', '65536'), ('PORT', '1.5'),
])
def test_invalid_hosted_settings_are_rejected(configured_env, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        configure()


def test_public_hosted_mode_is_explicit_and_keeps_gateway_guards(configured_env, monkeypatch, tmp_path):
    monkeypatch.setenv('ATLAS_PUBLIC_ACCESS', '1')
    monkeypatch.delenv('ATLAS_ACCESS_CODE')
    monkeypatch.setenv('ATLAS_ADDITIONAL_SITE_ORIGINS', 'https://portfolio.example')
    configure()
    assert os.environ['ATLAS_AUTH_ENABLED'] == '0'
    assert 'https://portfolio.example' in os.environ['ATLAS_ORIGINS'].split(',')
    app = create_app(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get('/api/state').status_code == 403
        response = client.get('/api/state', headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data['auth_enabled'] is False and data['user'] == 'Public reviewer'
        assert len(data['workspace']['sources']) == 3
        assert data['workspace']['analysis']
        assert 'set-cookie' not in response.headers
        assert not (tmp_path/'access-code').exists()
        assert client.post('/api/login', json={'name': 'A', 'passcode': ACCESS}, headers=HEADERS).status_code == 404
        revision = data['workspace']['revision']
        assert client.post('/api/analyze', json={'revision': revision}, headers=HEADERS).status_code == 200
        assert client.post('/api/analyze', json={'revision': revision}, headers=HEADERS).status_code == 409
        assert client.post('/api/analyze', json={'revision': revision}, headers={**HEADERS, 'Origin': 'https://evil.example'}).status_code == 403
        saved = app.state.store.read().model_dump(mode='json')
    restarted = create_app(tmp_path)
    with TestClient(restarted, base_url=ORIGIN) as client:
        assert client.get('/api/state', headers=HEADERS).json()['workspace'] == saved


@pytest.mark.parametrize('key,value', [('ATLAS_PUBLIC_ACCESS', 'yes'), ('ATLAS_ADDITIONAL_SITE_ORIGINS', 'https://portfolio.example/path')])
def test_public_settings_reject_ambiguous_values(configured_env, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        configure()
