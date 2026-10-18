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

from .models import Analysis, Claim, Edge, Graph, Node, Topic, Workspace, PassageAnalysis, PipelineSummary, PipelineEvaluation, digest, now
from .document_parser import parse_document
from .document_classifier import classify_documents, document_classifier, document_evaluation
from .technical_entities import extract_entities

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
    return [(str(model.classes_[int(s.argmax())]) if s.max() >= 0.4 else 'other', round(float(s.max()), 4)) for s in scores]


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


def discover_topics(claims):
    """NMF over prose only. Code/URLs must not manufacture dominant subjects."""
    texts = [re.sub(r'https?://\S+|`_?|[*#|]' , ' ', c.quote) if c.document.kind != 'code' else '' for c in claims]
    eligible = [i for i,t in enumerate(texts) if len(re.findall(r'\b[a-zA-Z]{3,}\b',t)) >= 4]
    if len(eligible) < 4 or len({texts[i].lower() for i in eligible}) < 4:
        return [], ['Too little varied prose to discover topics. Add more documentation; no topics were forced.']
    try:
        vectorizer = TfidfVectorizer(stop_words='english',max_features=3000,token_pattern=r'(?u)\b[a-zA-Z][a-zA-Z0-9_.-]*\b',
                                    max_df=.90,ngram_range=(1,2))
        matrix = vectorizer.fit_transform([texts[i] for i in eligible])
        count = min(4,max(1,len(eligible)//3),matrix.shape[1],len(eligible)-1)
        nmf = NMF(n_components=count,init='nndsvda',max_iter=1000,random_state=11)
        weights = nmf.fit_transform(matrix)
        vocabulary = vectorizer.get_feature_names_out()
        totals = weights.sum(axis=1,keepdims=True)
        membership = np.divide(weights,totals,out=np.zeros_like(weights),where=totals > 0)
        topics = []
        for i,index in enumerate(eligible):
            if totals[i,0] > 0:
                claims[index].topic = int(weights[i].argmax())+1
                claims[index].document.topic_strength = round(float(membership[i].max()),4)
        for i,component in enumerate(nmf.components_):
            members = [index for index in eligible if claims[index].topic == i+1]
            if not members or component.max() <= 0:
                continue
            top = [j for j in component.argsort()[::-1] if component[j] > 0][:6]
            representatives = sorted(members,key=lambda index:(-float(weights[eligible.index(index),i]),index))[:3]
            topics.append(Topic(id=i+1,terms=[str(vocabulary[j]) for j in top],
                weights=[round(float(component[j]/component.max()),4) for j in top],count=len(members),
                representatives=[claims[j].id for j in representatives],source_count=len({claims[j].source_id for j in members})))
        return topics, ['Topic terms are learned from prose in this workspace; code blocks remain outside topic modeling.']
    except ValueError:
        return [], ['Not enough usable vocabulary to discover topics. No topics were forced.']


def analyze(state: Workspace) -> Workspace:
    state = state.model_copy(deep=True)
    previous = {c.id: c.review for c in state.claims}
    claims = []
    used = {u.entity.lower() for u in state.usage}
    for source in state.sources:
        for block in parse_document(source.text):
            text = source.text[block.start:block.end]
            identifier = 'c-'+digest(source.id+'\0'+str(block.start)+'\0'+text)[:20]
            mentions = extract_entities(text,block.start)
            extracted = sorted(set(entities(text)) | {m.normalized for m in mentions})[:30]
            excerpt = re.sub(r'^\s*(?:[-+*]|\d+[.)])\s+', '', text)
            excerpt = re.sub(r'\s+', ' ', excerpt).replace('`','').strip()
            title = re.split(r'(?<=[.!?])\s+',excerpt,maxsplit=1)[0][:120]
            if block.kind in ('code','table'):
                title = (block.headings[-1] if block.headings else 'Source')+' · '+block.kind
            document = PassageAnalysis(title=title[:160] or 'Source passage',headings=list(block.headings),kind=block.kind,
                words=len(re.findall(r'\b\w+\b',text)),sentences=len(re.findall(r'[.!?](?:\s|$)',text)),mentions=mentions)
            claims.append(Claim(id=identifier, source_id=source.id, quote=text, start=block.start, end=block.end,
                entities=extracted,category='other',score=0,topic=0,applicable=bool(used.intersection(extracted)),
                review=previous.get(identifier),document=document))
    if not claims:
        raise ValueError('No analyzable text. Add paragraphs, lists or code below your headings.')
    if len(claims) > 200:
        raise ValueError('Analysis exceeds 200 claims/passages. Split the review into smaller workspaces.')
    # Preserve release signals as a separate compatibility layer, never as purpose labels.
    for claim,(label,score) in zip(claims,classify([c.quote for c in claims])):
        claim.category,claim.score = label,score
    inputs = [' > '.join(c.document.headings)+'\n'+c.quote for c in claims]
    for claim,result in zip(claims,classify_documents(inputs)):
        claim.document.purpose = result['purpose']
        claim.document.alternatives = result['alternatives']
        claim.document.examples = result['examples']
    topics,notices = discover_topics(claims)
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
    model = document_classifier()
    notices += ['Purpose scores are uncalibrated suggestions from synthetic training examples, not confidence or risk probabilities.',
                'Entity types come from explicit syntax rules. Documentation is not executed and application code is not inspected.',
                'Extraction keeps up to 60 typed mentions and 30 graph identifiers per passage. Full source text remains available.']
    evaluation = document_evaluation()
    pipeline = PipelineSummary(evaluation=PipelineEvaluation(**{key:evaluation[key] for key in ('held_out_examples','macro_f1','keyword_macro_f1','evaluation_hash')}),sources=len(state.sources),passages=len(claims),words=sum(c.document.words for c in claims),
        sections=len({(c.source_id,tuple(c.document.headings)) for c in claims}),code_blocks=sum(c.document.kind == 'code' for c in claims),
        entity_mentions=sum(len(c.document.mentions) for c in claims),
        unique_entities=len({(m.kind,m.normalized) for c in claims for m in c.document.mentions}),
        embedding_dimensions=model[1].n_components,training_examples=len(model[4]),notices=notices)
    state.analysis = Analysis(method='Structural Markdown/RST passages; TF-IDF + LSA/logistic purpose classification; NMF topics; typed entity rules',
        embedding_model='local-document-lsa-v1',training_hash=model[6],source_digest=source_digest(state),created_at=now(),pipeline=pipeline)
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
    by_id = {c.id: c for c in state.claims}
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
                if ident in by_id:
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
    source_by_id = {s.id: s for s in state.sources}
    return [{'claim': by_id[ident].model_dump(), 'source': {'title': source_by_id[by_id[ident].source_id].title, 'version': source_by_id[by_id[ident].source_id].version}, 'score': round(value[0], 4), 'reason': value[1]} for ident, value in sorted(ranked.items(), key=lambda item: (-item[1][0], item[0]))[:limit]]
