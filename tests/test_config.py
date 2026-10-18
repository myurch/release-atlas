"""Private startup configuration, using synthetic credentials only."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from backend.config import load_env


def test_private_env_loading_and_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('ATLAS_PORT', '8999')
    path = tmp_path / '.env'
    path.write_text('# private\nexport OPENAI_API_KEY="synthetic-key" # comment\nATLAS_PORT=8888\nATLAS_LLM_MODEL=demo # comment\n')
    monkeypatch.delenv('ATLAS_LLM_MODEL', raising=False)
    load_env(path)
    assert os.environ['OPENAI_API_KEY'] == 'synthetic-key'
    assert os.environ['ATLAS_PORT'] == '8999'
    assert os.environ['ATLAS_LLM_MODEL'] == 'demo'


def test_no_interpolation_or_execution(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    marker = tmp_path / 'must-not-exist'
    value = f'$(touch {marker})${{HOME}}`whoami`'
    path = tmp_path / '.env'
    path.write_text(f"OPENAI_API_KEY='{value}'\n")
    load_env(path)
    assert os.environ['OPENAI_API_KEY'] == value
    assert not marker.exists()


@pytest.mark.parametrize('line', ['PATH=/bad', 'OPENAI_API_KEY="unterminated', 'OPENAI_API_KEY="synthetic-key" extra'])
def test_invalid_configuration_does_not_reveal_values(tmp_path, line):
    path = tmp_path / '.env'
    path.write_text(line)
    with pytest.raises(ValueError) as error:
        load_env(path)
    assert line not in str(error.value)
    assert 'synthetic-key' not in str(error.value)


def test_missing_env_is_optional(tmp_path):
    load_env(tmp_path / 'missing')


def test_launcher_handoff_loads_root_env_without_echoing_key(tmp_path):
    backend = tmp_path / 'backend'
    backend.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'backend/config.py', backend / 'config.py')
    (tmp_path / '.env').write_text('OPENAI_API_KEY=synthetic-private-key\nATLAS_PORT=8888\n')
    env = {key: value for key, value in os.environ.items() if key not in ('OPENAI_API_KEY', 'ATLAS_PORT')}
    result = subprocess.run([sys.executable, str(backend / 'config.py'), sys.executable, '-c',
                             'import os; assert os.environ["OPENAI_API_KEY"] == "synthetic-private-key"; '
                             'assert os.environ["ATLAS_PORT"] == "8888"; '
                             'assert os.environ["RELEASE_ATLAS_ENV_LOADED"] == "1"; print("loaded")'],
                            cwd=tmp_path.parent, env=env, capture_output=True, text=True, check=True)
    assert result.stdout == 'loaded\n' and result.stderr == ''
