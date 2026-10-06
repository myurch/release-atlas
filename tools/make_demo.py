"""Build a reproducible offline demo from original, explicitly synthetic inputs."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.models import Source, SourceInput, Usage, Workspace
from backend.nlp import analyze

raw=json.loads((ROOT/'data/demo-input.json').read_text())
state=analyze(Workspace(title=raw['title'],sources=[Source.create(SourceInput(**s)) for s in raw['sources']],usage=[Usage(**u) for u in raw['usage']]))
state.analysis.created_at='2026-10-06T00:00:00+00:00'
(ROOT/'data/demo-snapshot.json').write_text(state.model_dump_json(indent=2)+'\n')
print('Built deterministic synthetic demo: 3 sources, 12 cited claims.')
