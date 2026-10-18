"""Versioned, bounded workspace contracts shared by persistence and imports."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_REVISION = 2**63-1
UNSAFE_CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @field_validator('*')
    @classmethod
    def valid_unicode(cls, value):
        def check(item):
            if isinstance(item, str):
                item.encode('utf-8')
                if UNSAFE_CONTROLS.search(item):
                    raise ValueError('Text contains unsupported control characters')
            elif isinstance(item, list):
                for child in item:
                    check(child)
        check(value)
        return value


class SourceInput(Strict):
    title: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=12000)
    url: str = Field(default='', max_length=1000)
    license: str = Field(default='User supplied; verify redistribution rights', max_length=300)

    @model_validator(mode='after')
    def meaningful(self):
        if not self.title.strip() or not self.version.strip() or not self.text.strip():
            raise ValueError('Title, version and source text must not be blank')
        if self.url and not self.url.startswith(('https://', 'http://')):
            raise ValueError('Source URL must be HTTP or HTTPS')
        return self


class Source(SourceInput):
    id: str = Field(max_length=80)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    @classmethod
    def create(cls, source: SourceInput):
        sha = digest(source.text)
        return cls(**source.model_dump(), id='s-'+digest(source.version+'\0'+sha)[:20], sha256=sha)


class Usage(Strict):
    component: str = Field(min_length=1, max_length=80)
    entity: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z_][A-Za-z0-9_.:/-]*$')


class Review(Strict):
    status: Literal['applicable', 'not-applicable', 'needs-investigation']
    note: str = Field(default='', max_length=2000)
    by: str = Field(min_length=1, max_length=60)
    at: str = Field(max_length=80)


Purpose = Literal['installation', 'configuration', 'api-reference', 'example', 'troubleshooting', 'security', 'migration', 'overview', 'resources', 'other']


class EntityMention(Strict):
    name: str = Field(min_length=1, max_length=100)
    normalized: str = Field(min_length=1, max_length=100)
    kind: Literal['api', 'configuration', 'command', 'endpoint', 'package', 'protocol', 'identifier']
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    rule: str = Field(min_length=1, max_length=80)


class PurposeScore(Strict):
    label: Purpose
    score: float = Field(ge=0, le=1)


class ClassificationExample(Strict):
    label: Purpose
    text: str = Field(min_length=1, max_length=400)
    similarity: float = Field(ge=-1, le=1)


class PassageAnalysis(Strict):
    title: str = Field(min_length=1, max_length=160)
    headings: list[Annotated[str, Field(max_length=160)]] = Field(default_factory=list, max_length=8)
    kind: Literal['paragraph', 'list-item', 'code', 'table']
    words: int = Field(ge=0)
    sentences: int = Field(ge=0)
    purpose: Purpose = 'other'
    alternatives: list[PurposeScore] = Field(default_factory=list, max_length=3)
    examples: list[ClassificationExample] = Field(default_factory=list, max_length=2)
    mentions: list[EntityMention] = Field(default_factory=list, max_length=60)
    topic_strength: float = Field(default=0, ge=0, le=1)


class Claim(Strict):
    id: str = Field(max_length=80)
    source_id: str = Field(max_length=80)
    quote: str = Field(min_length=1, max_length=12000)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    entities: list[Annotated[str, Field(max_length=100)]] = Field(max_length=30)
    category: Literal['breaking', 'deprecation', 'security', 'feature', 'fix', 'other']
    score: float = Field(ge=0, le=1)
    topic: int = Field(ge=0)
    applicable: bool = False
    conflicts: list[str] = Field(default_factory=list, max_length=200)
    review: Review | None = None
    document: PassageAnalysis | None = None


class Topic(Strict):
    id: int = Field(ge=0)
    terms: list[Annotated[str, Field(max_length=100)]] = Field(max_length=6)
    count: int = Field(ge=0)
    weights: list[Annotated[float, Field(ge=0, le=1)]] = Field(default_factory=list, max_length=6)
    representatives: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=3)
    source_count: int = Field(default=0, ge=0, le=30)


class PipelineEvaluation(Strict):
    held_out_examples: int = Field(ge=1, le=1000)
    macro_f1: float = Field(ge=0, le=1)
    keyword_macro_f1: float = Field(ge=0, le=1)
    evaluation_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


class PipelineSummary(Strict):
    version: Literal['documentation-v1'] = 'documentation-v1'
    evaluation: PipelineEvaluation | None = None
    sources: int = Field(ge=0, le=30)
    passages: int = Field(ge=0, le=200)
    words: int = Field(ge=0)
    sections: int = Field(ge=0)
    code_blocks: int = Field(ge=0, le=200)
    entity_mentions: int = Field(ge=0, le=12000)
    unique_entities: int = Field(ge=0, le=12000)
    embedding_dimensions: int = Field(ge=1, le=300)
    training_examples: int = Field(ge=1, le=1000)
    notices: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=6)


class Node(Strict):
    id: str = Field(max_length=240)
    label: str = Field(max_length=240)
    kind: Literal['claim', 'entity', 'source', 'component']
    degree: int = Field(ge=0)


class Edge(Strict):
    source: str = Field(max_length=240)
    target: str = Field(max_length=240)
    relation: Literal['supports', 'mentions', 'uses', 'conflicts']


class Graph(Strict):
    nodes: list[Node] = Field(default_factory=list, max_length=7000)
    edges: list[Edge] = Field(default_factory=list, max_length=15000)


class Analysis(Strict):
    method: str = Field(max_length=300)
    embedding_model: str = Field(max_length=200)
    training_hash: str = Field(max_length=64)
    source_digest: str = Field(max_length=64)
    created_at: str = Field(max_length=80)
    pipeline: PipelineSummary | None = None


class Answer(Strict):
    id: str = Field(max_length=80)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(max_length=8000)
    citations: list[str] = Field(max_length=12)
    uncertainty: str = Field(max_length=2000)
    method: str = Field(max_length=200)
    at: str = Field(max_length=80)


class Audit(Strict):
    at: str = Field(max_length=80)
    by: str = Field(max_length=60)
    action: str = Field(max_length=200)
    revision: int = Field(ge=0, le=MAX_REVISION, strict=True)


class Workspace(Strict):
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0, le=MAX_REVISION, strict=True)
    title: str = Field(default='Untitled review', min_length=1, max_length=160)
    sources: list[Source] = Field(default_factory=list, max_length=30)
    usage: list[Usage] = Field(default_factory=list, max_length=40)
    claims: list[Claim] = Field(default_factory=list, max_length=200)
    topics: list[Topic] = Field(default_factory=list, max_length=8)
    graph: Graph = Field(default_factory=Graph)
    analysis: Analysis | None = None
    answers: list[Answer] = Field(default_factory=list, max_length=30)
    audit: list[Audit] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def integrity(self):
        if sum(len(s.text) for s in self.sources) > 300000:
            raise ValueError('Workspace exceeds 300,000 source characters')
        sources = {s.id: s for s in self.sources}
        claims = {c.id: c for c in self.claims}
        if len(sources) != len(self.sources) or len(claims) != len(self.claims):
            raise ValueError('Duplicate source or claim identifier')
        for s in self.sources:
            canonical = Source.create(SourceInput(**s.model_dump(exclude={'id', 'sha256'})))
            if s.id != canonical.id or s.sha256 != canonical.sha256:
                raise ValueError('Source content hash or identity mismatch')
        for c in self.claims:
            source = sources.get(c.source_id)
            if source is None or c.end <= c.start or source.text[c.start:c.end] != c.quote:
                raise ValueError('Claim citation does not match source text')
            if c.id != 'c-'+digest(c.source_id+'\0'+str(c.start)+'\0'+c.quote)[:20]:
                raise ValueError('Claim identity mismatch')
            if c.document:
                for mention in c.document.mentions:
                    if (mention.start < c.start or mention.end > c.end or mention.end <= mention.start
                            or source.text[mention.start:mention.end] != mention.name
                            or mention.normalized != mention.name.removesuffix('()').lower()):
                        raise ValueError('Entity mention does not match source text')
            if any(x not in claims or x == c.id for x in c.conflicts):
                raise ValueError('Invalid conflict reference')
        for topic in self.topics:
            if any(ident not in claims or claims[ident].topic != topic.id for ident in topic.representatives):
                raise ValueError('Invalid topic representative')
            if topic.weights and len(topic.weights) != len(topic.terms):
                raise ValueError('Topic weights must match terms')
        for n in self.graph.nodes:
            if (n.kind == 'claim' and n.id not in claims) or (n.kind == 'source' and n.id not in sources):
                raise ValueError('Graph references a missing source or claim')
        nodes = {n.id for n in self.graph.nodes}
        if len(nodes) != len(self.graph.nodes):
            raise ValueError('Duplicate graph node')
        if any(e.source not in nodes or e.target not in nodes for e in self.graph.edges):
            raise ValueError('Dangling graph edge')
        if any(x not in claims for a in self.answers for x in a.citations):
            raise ValueError('Unknown answer citation')
        if len(self.model_dump_json().encode('utf-8')) > 1_800_000:
            raise ValueError('Saved workspace exceeds 1.8 MB; reduce source or graph content')
        return self
