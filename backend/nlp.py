"""Inspectable statistical NLP and cited graph construction, without remote models."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import networkx as nx
import numpy as np
from sklearn.decomposition import NMF, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import normalize

from .models import Analysis, Claim, Edge, Graph, Node, Topic, Workspace, digest, now

DATA = Path(__file__).resolve().parents[1] / 'data'
TOKEN_PATTERN = r'(?u)\b[a-zA-Z_][a-zA-Z0-9_.-]*\b'


def entities(text: str) -> list[str]:
    quoted = re.findall(r'`([A-Za-z_][A-Za-z0-9_.:/-]{0,99})`', text)
    identifiers = re.findall(r'\b(?:[a-z]+_[a-zA-Z0-9_]+|[a-z]+[A-Z][a-zA-Z0-9]*)\b', text)
    return sorted({s.lower() for s in quoted + identifiers})[:30]


@lru_cache(maxsize=1)
def classifier():
    raw = (DATA / 'training.json').read_text()
    samples = json.loads(raw)['examples']
    labels, texts = zip(*samples)
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=TOKEN_PATTERN)
    matrix = vectorizer.fit_transform(texts)
    projector = TruncatedSVD(n_components=min(24, len(texts)-1), random_state=11)
    embedded = normalize(projector.fit_transform(matrix))
    model = LogisticRegression(C=12, max_iter=1000, random_state=11).fit(embedded, labels)
    return vectorizer, projector, model, digest(raw)


def classify(texts: list[str]):
    vectorizer, projector, model, _ = classifier()
    vectors = normalize(projector.transform(vectorizer.transform(texts)))
    scores = model.predict_proba(vectors)
    return [(str(model.classes_[int(s.argmax())]), round(float(s.max()), 4)) for s in scores]


def source_digest(state: Workspace) -> str:
    return digest(json.dumps([[s.id, s.sha256] for s in state.sources] + [u.model_dump() for u in state.usage], sort_keys=True))


def assertion(text: str, entity: str) -> str | None:
    """Conservative candidate detector, not a general natural-language reasoner."""
    text = text.lower()
    escaped = re.escape(entity)
    if re.search(rf'(?:removed|deleted)\s+`?{escaped}\b', text) or re.search(rf'`?{escaped}`?.{{0,24}}(?:no longer supported|was removed|was deleted)', text):
        return 'removed'
    if re.search(rf'`?{escaped}`?.{{0,35}}(?:remains supported|is supported|still supported|is available)', text):
        return 'supported'
    return None


def make_graph(state: Workspace) -> Graph:
    graph = nx.Graph()
    for s in state.sources:
        graph.add_node(s.id, label=s.title, kind='source')
    for claim in state.claims:
        graph.add_node(claim.id, label=claim.quote[:100], kind='claim')
        graph.add_edge(claim.source_id, claim.id, relation='supports')
        for entity in claim.entities:
            eid = 'e:'+entity
            graph.add_node(eid, label=entity, kind='entity')
            graph.add_edge(claim.id, eid, relation='mentions')
        for other in claim.conflicts:
            graph.add_edge(claim.id, other, relation='conflicts')
    for usage in state.usage:
        cid = 'u:'+usage.component
        eid = 'e:'+usage.entity.lower()
        graph.add_node(cid, label=usage.component, kind='component')
        graph.add_node(eid, label=usage.entity.lower(), kind='entity')
        graph.add_edge(cid, eid, relation='uses')
    return Graph(
        nodes=[Node(id=n, label=d['label'], kind=d['kind'], degree=graph.degree[n]) for n, d in sorted(graph.nodes(data=True))],
        edges=[Edge(source=a, target=b, relation=d['relation']) for a, b, d in sorted(graph.edges(data=True))],
    )


def analyze(state: Workspace) -> Workspace:
    state = state.model_copy(deep=True)
    previous = {c.id: c.review for c in state.claims}
    claims = []
    used = {u.entity.lower() for u in state.usage}
    for source in state.sources:
        for match in re.finditer(r'[^\r\n]+', source.text):
            text = match.group().strip()
            if not text or text.startswith('#'):
                continue
            start = match.start()+len(match.group())-len(match.group().lstrip())
            identifier = 'c-'+digest(source.id+'\0'+str(start)+'\0'+text)[:20]
            extracted = entities(text)
            claims.append(Claim(id=identifier, source_id=source.id, quote=text, start=start, end=start+len(text), entities=extracted, category='other', score=0, topic=0, applicable=bool(used.intersection(extracted)), review=previous.get(identifier)))
    if not claims:
        raise ValueError('No analyzable text. Add non-heading source lines.')
    if len(claims) > 200:
        raise ValueError('Analysis exceeds 200 claims. Split the review into smaller workspaces.')
    predictions = classify([c.quote for c in claims])
    for claim, (label, score) in zip(claims, predictions):
        claim.category, claim.score = label, score
    texts = [c.quote for c in claims]
    topics = []
    try:
        vectorizer = TfidfVectorizer(stop_words='english', max_features=3000, token_pattern=TOKEN_PATTERN)
        matrix = vectorizer.fit_transform(texts)
        count = min(4, len(claims), matrix.shape[1])
        nmf = NMF(n_components=count, init='nndsvda', max_iter=600, random_state=11)
        weights = nmf.fit_transform(matrix)
        vocabulary = vectorizer.get_feature_names_out()
        assignments = weights.argmax(axis=1)
        for claim, topic in zip(claims, assignments):
            claim.topic = int(topic)
        topics = [Topic(id=i, terms=[str(vocabulary[j]) for j in component.argsort()[-4:][::-1]], count=int((assignments == i).sum())) for i, component in enumerate(nmf.components_)]
    except ValueError:
        topics = [Topic(id=0, terms=['unassigned'], count=len(claims))]
    sources = {s.id: s for s in state.sources}
    for i, left in enumerate(claims):
        for right in claims[i+1:]:
            version = sources[left.source_id].version
            if version != sources[right.source_id].version or not re.fullmatch(r'v?\d+(?:\.\d+){1,3}(?:[-+][\w.]+)?', version):
                continue
            for entity in set(left.entities).intersection(right.entities):
                a, b = assertion(left.quote, entity), assertion(right.quote, entity)
                if a and b and a != b:
                    left.conflicts.append(right.id)
                    right.conflicts.append(left.id)
                    break
    state.claims, state.topics, state.answers = claims, topics, []
    state.graph = make_graph(state)
    state.analysis = Analysis(method='TF-IDF + LSA/logistic classification; NMF topics; technical identifier extraction', embedding_model='local-lsa-v1', training_hash=classifier()[3], source_digest=source_digest(state), created_at=now())
    return Workspace.model_validate(state.model_dump())


def retrieve(state: Workspace, question: str, mode: str = 'graph', limit: int = 6, external_vectors=None):
    if not state.claims:
        return []
    texts = [c.quote for c in state.claims]
    try:
        if external_vectors is not None:
            matrix = normalize(np.asarray(external_vectors, dtype=float))
            if matrix.shape[0] != len(texts)+1:
                raise ValueError('Embedding count mismatch')
            scores = matrix[:-1] @ matrix[-1]
        else:
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), token_pattern=TOKEN_PATTERN)
            matrix = vectorizer.fit_transform(texts)
            query = vectorizer.transform([question])
            if mode == 'lexical' or min(matrix.shape) < 3:
                scores = (matrix @ query.T).toarray().ravel()
            else:
                projector = TruncatedSVD(n_components=min(32, matrix.shape[0]-1, matrix.shape[1]-1), random_state=11)
                doc_vectors = normalize(projector.fit_transform(matrix))
                query_vector = normalize(projector.transform(query))
                scores = (doc_vectors @ query_vector.T).ravel()
    except ValueError as exc:
        if external_vectors is not None:
            raise exc
        scores = np.zeros(len(texts))
    ranked = {c.id: (max(0.0, float(score)), 'text similarity') for c, score in zip(state.claims, scores) if score > 0.04}
    if mode == 'graph':
        graph = nx.Graph()
        for e in state.graph.edges:
            if e.relation != 'supports':
                graph.add_edge(e.source, e.target)
        question_lower = question.lower()
        seeds = [n for n in state.graph.nodes if n.kind in ('entity', 'component') and n.label.lower() in question_lower]
        for node in seeds:
            if node.id not in graph:
                continue
            for ident, distance in nx.single_source_shortest_path_length(graph, node.id, cutoff=3).items():
                if ident.startswith('c-'):
                    score = 1.0/(1+distance/4)
                    if score > ranked.get(ident, (0, ''))[0]:
                        ranked[ident] = (score, f'{node.label}: graph path of {distance} edge(s)')
        # Bring both sides of a cited conflict into the result set.
        by_id = {c.id: c for c in state.claims}
        for ident, (score, _) in list(ranked.items()):
            for other in by_id[ident].conflicts:
                if other not in ranked:
                    ranked[other] = (score*0.95, 'conflicting cited claim')
    by_id = {c.id: c for c in state.claims}
    return [{'claim': by_id[ident].model_dump(), 'score': round(value[0], 4), 'reason': value[1]} for ident, value in sorted(ranked.items(), key=lambda item: (-item[1][0], item[0]))[:limit]]
