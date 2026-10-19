"""Bounded local import of original fictional, versioned documentation."""
from pathlib import Path
from typing import Literal

from pydantic import Field

from .input_validation import json_object
from .models import Source, SourceInput, Strict, digest

BUNDLE_DIR = Path(__file__).resolve().parents[1]/'data/demo-documents'
PROJECTS = (('demo/lumenui', 'LumenUI', 'frontend'), ('demo/harborapi', 'HarborAPI', 'backend'))
VERSIONS = ('1.0', '2.0', '3.0')
DEMO_DOCUMENT_KEYS = tuple(f'{repo}@{version}' for repo, _, _ in PROJECTS for version in VERSIONS)


class DemoDocument(Strict):
    repository: Literal['demo/lumenui', 'demo/harborapi']
    version: Literal['1.0', '2.0', '3.0']
    title: str = Field(min_length=1, max_length=160)
    path: str = Field(min_length=1, max_length=80)
    url: str = Field(max_length=1000)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class DemoBundle(Strict):
    documents: list[DemoDocument] = Field(min_length=6, max_length=6)


def load_demo_documents():
    """Validate every fixed file and hash before preparing a single database write."""
    with (BUNDLE_DIR/'manifest.json').open('rb') as stream:
        raw = stream.read(20_001)
    if len(raw) > 20_000:
        raise ValueError('Demo manifest exceeds supported limits')
    bundle = DemoBundle.model_validate(json_object(raw))
    sources = []
    for entry, (repo, name, role, version) in zip(bundle.documents,
            ((repo, name, role, version) for repo, name, role in PROJECTS for version in VERSIONS)):
        filename = f'{repo.split("/")[1]}-{version}.md'
        origin = f'https://example.invalid/{repo}/blob/v{version}/README.md'
        if (entry.repository != repo or entry.version != version or entry.path != filename
                or entry.title != f'{name} {role} documentation' or entry.url != origin):
            raise ValueError('Invalid synthetic documentation manifest')
        # Never use an unchecked manifest path to read a file.
        with (BUNDLE_DIR/filename).open('rb') as stream:
            raw_text = stream.read(48_001)
        if len(raw_text) > 48_000:
            raise ValueError('Demo document exceeds supported limits')
        text = raw_text.decode('utf-8')
        if digest(text) != entry.sha256:
            raise ValueError('Demo document hash mismatch')
        source = Source.create(SourceInput(title=entry.title, version=version, url=origin,
            license='MIT; original synthetic documentation for Release Atlas by Maryana Yurchyshyna', text=text))
        sources.append((f'{repo}@{version}', source))
    return sources
