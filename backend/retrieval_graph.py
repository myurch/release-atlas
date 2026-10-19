"""Bounded, evidence-backed passage/entity traversal. No model or network calls."""
from __future__ import annotations

from collections import defaultdict
import re

import networkx as nx
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from .technical_entities import extract_entities

# These names are too broad to act as technology identities or useful bridges.
GENERIC = set(ENGLISH_STOP_WORDS) | set('''api application authentication authorization backend client code configuration database documentation documents example examples frontend getting guide identity installation introduction json library logging overview package project python readme reference release releases report security server settings setup source sql storage templates text tutorial usage user version web http https wsgi asgi ssl tls tcp csv utf-8 main print request response localhost session cookie token password credentials hash connection pool migration installing'''.split())
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{2,79}')


def mentions(text, name):
    return bool(re.search(r'(?<![\w.-])'+re.escape(name)+r'(?![\w-]|\.\w)', text, re.I))


def source_aliases(rows):
    """Resolve source identities from distinctive leading title names, never titles in prose."""
    owners = defaultdict(set)
    for row in rows:
        repository = re.match(r'^([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)(?:\s|$)', row.title)
        names = [repository[2]] if repository else NAME.findall(row.title)
        # A title such as "Flask 3.0 documentation" can identify Flask. Do not
        # infer that every noun in an arbitrary title names a technology.
        if names:
            name = names[0].casefold().rstrip('.')
            suffix = {part.casefold().rstrip('.') for part in names[1:] if not re.fullmatch(r'v?\d[\w.-]*', part, re.I)}
            labels = set('docs documentation readme guide reference api sdk library release notes manual tutorial framework web template templates templating engine'.split())
            if name not in GENERIC and (repository or suffix <= labels):
                owners[name].add(row.passage.source_id)
    return owners


def build_graph(rows, entity_sets=None, *, owners=None):
    graph = nx.DiGraph()
    owners = source_aliases(rows) if owners is None else owners
    if entity_sets is None:
        entity_sets = [{m.normalized for m in extract_entities(row.passage.quote)} for row in rows]
    typed = [{name for name in names if name not in GENERIC and re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_.:/-]{3,99}', name)} for names in entity_sets]
    source_frequency = defaultdict(set)
    identifier_rows = defaultdict(list)
    for i, (row, names) in enumerate(zip(rows, typed)):
        for name in names:
            source_frequency[name].add(row.passage.source_id)
            identifier_rows[name].append(i)
    for i, row in enumerate(rows):
        graph.add_node(i, kind='passage', source_id=row.passage.source_id)
    # Technology-reference edges point from an exact mention to passages in a
    # source identified by its title. Ambiguous identities never create edges.
    for name, source_ids in sorted(owners.items()):
        if len(source_ids) != 1:
            continue
        owner = next(iter(source_ids))
        node = ('reference', name)
        targets = [i for i,r in enumerate(rows) if r.passage.source_id == owner]
        origins = [i for i,r in enumerate(rows) if r.passage.source_id != owner and mentions(r.passage.quote, name)]
        if not origins:
            continue
        for i in origins:
            graph.add_edge(i, node, relation='technology reference')
        for i in targets:
            graph.add_edge(node, i, relation='technology reference')
    # Shared exact identifiers provide a second kind of connection. High-degree
    # identifiers and ordinary prose are deliberately excluded.
    for name, source_ids in sorted(source_frequency.items()):
        if not 2 <= len(source_ids) <= 3:
            continue
        node = ('identifier', name)
        for i in identifier_rows[name]:
            graph.add_edge(i, node, relation='shared identifier')
            graph.add_edge(node, i, relation='shared identifier')
    return graph


def expand(graph, rows, order, allowed, lexical, dense, vectors, neural):
    """One entity bridge, three seed passages, two new sources, no recursion."""
    if not order:
        return []
    baseline_sources = {rows[i].passage.source_id for i in order[:8]}
    proposed = []
    for seed in order[:3]:
        for bridge in graph.successors(seed):
            for target in graph.successors(bridge):
                source_id = rows[target].passage.source_id
                if source_id not in allowed or source_id in baseline_sources:
                    continue
                if rows[seed].passage.source_id == source_id:
                    continue
                similarity = float(vectors[seed] @ vectors[target])
                relation = graph[seed][bridge]['relation']
                # An explicit reference may recover context missed by the query.
                # Shared identifiers require additional direct query relevance.
                direct = lexical[target] > 0 or dense[target] > (.22 if neural else .12)
                seed_words={w.casefold().rstrip('.') for w in NAME.findall(rows[seed].passage.quote)}-GENERIC-{bridge[1]}
                target_words={w.casefold().rstrip('.') for w in NAME.findall(rows[target].passage.quote)}-GENERIC-{bridge[1]}
                # Repeated source sections can depress TF-IDF cosine even when
                # two independent content terms corroborate the exact reference.
                contextual = similarity > (.30 if neural else .12) or len(seed_words & target_words)>=2
                if not direct and not (relation == 'technology reference' and contextual):
                    continue
                if relation == 'shared identifier' and not contextual:
                    continue
                value = .55*max(0., float(dense[target])) + .35*max(0., similarity) + (.10 if relation == 'technology reference' else .04)
                proposed.append((value, target, seed, bridge[1], relation))
    chosen=[]
    seen_sources=set()
    for value,target,seed,via,relation in sorted(proposed, key=lambda p:(-p[0],p[1],p[2],p[3])):
        if rows[target].passage.source_id in seen_sources:
            continue
        chosen.append((target,seed,via,relation))
        seen_sources.add(rows[target].passage.source_id)
        if len(chosen) == 2:
            break
    return chosen


def selected_connections(rows, all_rows, vectors, neural, expansion_paths=(), *, reference_graph=None):
    """Display supported paths among selected quotes without altering retrieval."""
    graph = build_graph(rows, owners=source_aliases(all_rows))
    positions = {row.passage.id:i for i,row in enumerate(all_rows)}
    preferred = {(p.from_passage,p.to_passage,p.via,p.relation) for p in expansion_paths}
    proposals=[]
    for origin,row in enumerate(rows):
        for bridge in graph.successors(origin):
            if reference_graph is not None and bridge not in reference_graph:
                continue
            for target in graph.successors(bridge):
                other=rows[target]
                if row.passage.source_id == other.passage.source_id:
                    continue
                via=bridge[1]
                relation=graph[origin][bridge]['relation']
                key=(row.passage.id,other.passage.id,via,relation)
                similarity=0.
                if row.passage.id in positions and other.passage.id in positions:
                    similarity=float(vectors[positions[row.passage.id]]@vectors[positions[other.passage.id]])
                words=lambda text: {w.casefold().rstrip('.') for w in NAME.findall(text)}-GENERIC-{via}
                contextual=similarity > (.30 if neural else .12) or len(words(row.passage.quote)&words(other.passage.quote))>=2
                if relation == 'technology reference' and not contextual and key not in preferred:
                    continue
                # Shared exact identifiers are supported by both selected quotes.
                proposals.append((key in preferred,relation=='technology reference',similarity,origin,target,via,relation))
    result=[];seen=set()
    for preferred,reference,similarity,origin,target,via,relation in sorted(proposals,key=lambda p:(-p[0],-p[1],-p[2],p[3],p[4],p[5])):
        pair=tuple(sorted((rows[origin].passage.source_id,rows[target].passage.source_id)))
        key=(pair,via,relation)
        if key in seen:
            continue
        seen.add(key)
        result.append({'from_passage':rows[origin].passage.id,'to_passage':rows[target].passage.id,'via':via,'relation':relation})
        if len(result)==12:
            break
    return result
