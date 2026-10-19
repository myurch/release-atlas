"""Cached hybrid retrieval over immutable sources, independent of saved findings."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import re
import warnings
from typing import Literal

import numpy as np
from pydantic import Field
from sklearn.decomposition import NMF, TruncatedSVD
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import normalize
from packaging.version import Version, InvalidVersion

from .models import Strict, Workspace
from .document_parser import parse_document
from .document_classifier import document_classifier
from .technical_entities import extract_entities
from . import semantic, retrieval_graph

PASSAGE_SIZE=2000
PASSAGE_OVERLAP=100
MAX_PASSAGES=8
MAX_SOURCE_TEXT=16000
WINDOW=1000
REASONS=Literal['lexical match','semantic match','statistical similarity','exact entity','related topic','purpose match','selected source','source overview','conflict partner','neighboring context','terminology match','graph connection']


class SourcePassage(Strict):
    id: str
    source_id: str
    sha256: str
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    quote: str = Field(min_length=1,max_length=PASSAGE_SIZE)


class RetrievedPassage(SourcePassage):
    reasons: list[REASONS] = Field(max_length=8)


class GraphPath(Strict):
    from_passage: str = Field(max_length=200)
    to_passage: str = Field(max_length=200)
    via: str = Field(min_length=1,max_length=100)
    relation: Literal['technology reference','shared identifier']


class RetrievalReport(Strict):
    connections: list[GraphPath] = Field(default_factory=list,max_length=12)
    graph_paths: list[GraphPath] = Field(default_factory=list,max_length=2)
    encoder: Literal['neural-minilm','statistical-lsa']
    mode: Literal['focused','overview']
    model: str = Field(max_length=120)
    included_sources: int = Field(ge=0,le=30)
    total_sources: int = Field(ge=0,le=30)
    candidate_count: int = Field(ge=0,le=600)
    partial: bool
    fallback: str = Field(default='',max_length=300)
    notices: list[str] = Field(default_factory=list,max_length=6)
    passages: list[RetrievedPassage] = Field(default_factory=list,max_length=8)


INTENTS={
 'installation':'How do I install this package and get started? Setup requirements and dependencies.',
 'configuration':'How do I configure this setting? What default value or environment variable should I use?',
 'api-reference':'What methods endpoints and parameters are available? What does this API return?',
 'example':'Show me a code example. How do I implement this in an application?',
 'troubleshooting':'Why does this fail? Diagnose an error and fix a broken request.',
 'security':'What security precautions protect secrets and prevent attacks?',
 'migration':'What must change when upgrading? Which old APIs were removed or deprecated?',
 'overview':'What does this project do? Explain its features and architecture.',
 'resources':'Where are the documentation, project links, license and support channels?',
}
# Explicit terminology expansion is labeled separately from neural semantics.
TERMINOLOGY=[{'authentication','authenticate','login','signin','credentials','identity','password','oauth','oidc','saml'},
             {'authorization','permissions','privileges','rbac','access'},
             {'timeout','timeouts','deadline'}, {'installation','install','setup'}]


@dataclass
class Candidate:
    passage: SourcePassage
    headings: str
    kind: str
    title: str

    def input(self):
        return (self.title[:160]+'\n'+self.headings[-350:]+'\n'+self.passage.quote)[:1600]


def windows(source,start,end,heading='',kind='paragraph'):
    while start<end:
        stop=min(start+WINDOW,end)
        if stop<end:
            boundary=source.text.rfind('\n',start+600,stop)
            if boundary<start+600: boundary=source.text.rfind(' ',start+600,stop)
            if boundary>=start+600: stop=boundary
        if source.text[start:stop].strip():
            p=SourcePassage(id=f'p-{source.id}-{start}-{stop}',source_id=source.id,sha256=source.sha256,start=start,end=stop,quote=source.text[start:stop])
            yield Candidate(p,heading,kind,source.title)
        if stop==end: break
        start=max(start+1,stop-PASSAGE_OVERLAP)


def candidates_for(sources):
    rows=[]
    for source in sources:
        blocks=parse_document(source.text)
        if not blocks or len(blocks)>200:
            rows.extend(windows(source,0,len(source.text)))
            continue
        groups=[]
        for b in blocks:
            if (groups and b.kind!='code' and groups[-1][3]!='code' and b.headings==groups[-1][2]
                    and b.end-groups[-1][0]<=WINDOW):
                groups[-1]=(groups[-1][0],b.end,b.headings,'paragraph')
            else: groups.append((b.start,b.end,b.headings,b.kind))
        for start,end,heading,kind in groups:
            rows.extend(windows(source,start,end,' > '.join(heading),kind))
    if len(rows)>600:
        rows=[row for source in sources for row in windows(source,0,len(source.text))]
    return rows[:600]


@dataclass
class Index:
    rows: list[Candidate]
    vectorizer: object
    matrix: object
    metadata: object
    vectors: np.ndarray
    projector: object
    config: object
    fallback: str
    purpose_model: object
    purpose_vectors: np.ndarray
    intent_vectors: np.ndarray
    topic_weights: np.ndarray
    topic_vectors: np.ndarray
    entity_sets: list[set[str]]
    token_sets: list[set[str]]
    graph: object


@lru_cache(maxsize=2)
def neural_purpose(config):
    _,_,_,_,labels,texts,_=document_classifier()
    vectors=semantic.encode(list(texts)+list(INTENTS.values()),config)
    model=LogisticRegression(C=8,max_iter=1000,random_state=11).fit(vectors[:len(texts)],labels)
    return model,vectors[len(texts):]


@lru_cache(maxsize=3)
def build_index(key,config,fallback):
    from .models import Source
    sources=[Source.model_validate(row) for row in json.loads(key)]
    rows=candidates_for(sources)
    inputs=[row.input() for row in rows]
    if not rows: return None
    vectorizer=TfidfVectorizer(stop_words='english',ngram_range=(1,2),sublinear_tf=True,token_pattern=r'(?u)\b\w[\w.-]*\b')
    # Fixed anchors make empty/non-Latin corpora indexable without fabricating relevance.
    matrix=vectorizer.fit_transform([r.passage.quote for r in rows]+['atlas empty vocabulary anchor'])[:-1]
    metadata=vectorizer.transform([r.title+' '+r.headings for r in rows])
    projector=None
    if config:
        vectors=semantic.encode(inputs,config)
        model,intents=neural_purpose(config)
        purpose_vectors=model.predict_proba(vectors)
    else:
        projector=TruncatedSVD(n_components=max(1,min(48,matrix.shape[0],matrix.shape[1]-1)),random_state=11)
        # Include an anchor row to keep SVD valid even for a one-word source.
        fit=vectorizer.transform([r.passage.quote for r in rows]+['atlas empty vocabulary anchor'])
        projector.fit(fit)
        vectors=normalize(projector.transform(matrix))
        v,p,model,_,_,_,_=document_classifier()
        purpose_vectors=model.predict_proba(normalize(p.transform(v.transform(inputs))))
        intents=np.zeros((len(INTENTS),vectors.shape[1]))
    topic_weights=np.zeros((len(rows),0))
    topic_vectors=np.zeros((0,vectors.shape[1]))
    prose=[i for i,r in enumerate(rows) if r.kind!='code' and len(r.passage.quote.split())>=8]
    if len(prose)>=4 and len({rows[i].passage.quote for i in prose})>=4:
        try:
            tv=TfidfVectorizer(stop_words='english',max_features=2000,max_df=.95,token_pattern=r'(?u)\b[a-zA-Z][a-zA-Z_]{2,}\b')
            texts=[re.sub(r'https?://\S+',' ',rows[i].passage.quote) for i in prose]
            tm=tv.fit_transform(texts)
            if np.unique(np.round(tm.toarray(),5),axis=0).shape[0]<4: raise ValueError('Repetitive corpus')
            nmf=NMF(n_components=min(4,max(1,len(prose)//3),tm.shape[1]),init='nndsvda',max_iter=400,random_state=11)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always',ConvergenceWarning)
                weights=nmf.fit_transform(tm)
            if caught or not np.isfinite(weights).all(): raise ValueError('Unstable topics')
            weights=weights/np.maximum(weights.sum(axis=1,keepdims=True),1e-12)
            topic_weights=np.zeros((len(rows),weights.shape[1]))
            topic_weights[prose]=weights
            topic_vectors=normalize(topic_weights.T@vectors)
        except ValueError: pass
    entity_sets=[{m.normalized for m in extract_entities(r.passage.quote)} for r in rows]
    return Index(rows,vectorizer,matrix,metadata,vectors,projector,config,fallback,model,purpose_vectors,intents,topic_weights,topic_vectors,
                 entity_sets,
                 [set(re.findall(r'\w+',r.passage.quote.casefold())) for r in rows], retrieval_graph.build_graph(rows,entity_sets))


def get_index(state):
    key=json.dumps([s.model_dump() for s in state.sources],ensure_ascii=False,sort_keys=True)
    try:
        config,notice=semantic.configuration()
        return build_index(key,config,notice)
    except semantic.SemanticUnavailable as exc:
        return build_index(key,None,str(exc))


def effective_query(question,history=()):
    # New standalone questions must not keep unrelated earlier subjects alive.
    followup=re.search(r'\b(?:it|its|they|them|those|these|same|remaining|instead)\b|^(?:and |what about|how about)',question,re.I)
    prior=[m.content if hasattr(m,'content') else str(m) for m in history if not hasattr(m,'role') or m.role=='user']
    return (' '.join(prior[-2:])+' '+question)[-2400:] if followup else question


def scoped_sources(state,question,selected):
    allowed={s.id for s in state.sources}
    notices=[]
    if re.search(r'\b(?:only|exclusively)\b',question,re.I):
        hits=[(s.id,m.start(),m.end()) for s in state.sources for m in re.finditer(r'(?<!\w)'+re.escape(s.title)+r'(?!\w)',question,re.I)]
        named={sid for sid,start,end in hits if not any(left<=start and end<=right and (left,right)!=(start,end) for _,left,right in hits)}
        named |= {s.id for s in state.sources if s.id in question}
        if named: allowed &= named
        elif re.search(r'\b(?:this|selected)\s+(?:source|document)\b',question,re.I) and selected: allowed &= {selected}
        elif re.search(r'\bonly\s+(?:the\s+)?(?:source|document)\b',question,re.I):
            allowed=set();notices.append('The explicit source restriction could not be resolved. Use its exact title or select the source.')
    versions=list(re.finditer(r'\bversion\s+["\']?(v?\d+(?:\.\d+){0,3}(?:[-+][\w.-]+)?)',question,re.I))
    versions=[m for m in versions if not re.search(r'(?:python|http|tls)\s+$',question[max(0,m.start()-12):m.start()],re.I)]
    named_versions=set()
    for source in state.sources:
        matches=list(re.finditer(r'\bversion\s+["\']?'+re.escape(source.version)+r'(?![\w:-]|\.\w)',question,re.I))
        if any(not re.search(r'(?:python|http|tls)\s+$',question[max(0,m.start()-12):m.start()],re.I) for m in matches):
            named_versions.add(source.version.casefold())
    if named_versions:
        allowed &= {s.id for s in state.sources if s.version.casefold() in named_versions}
    unknown=re.search(r'\b(?:only|use|using)\s+(?:the\s+)?version\s+["\']?([^\s"\']+)',question,re.I)
    if unknown and not versions and not named_versions:
        allowed=set();notices.append('No source matches the requested version label. Specify an exact saved version.')
    if versions:
        targets={m[1].rstrip('.').lower().removeprefix('v') for m in versions}
        allowed &= {s.id for s in state.sources if s.version.lower().removeprefix('v') in targets}
    if re.search(r'\b(?:highest|latest|newest)\s+(?:source\s+)?version\b',question,re.I):
        versions=[]
        for s in state.sources:
            try: versions.append((Version(s.version),s.id))
            except InvalidVersion: pass
        if versions:
            maximum=max(v for v,sid in versions if sid in allowed) if any(sid in allowed for v,sid in versions) else None
            allowed &= {sid for v,sid in versions if v==maximum}
        else:
            allowed=set();notices.append('Source version labels cannot be ordered reliably. Specify the version to use.')
    if re.search(r'\b(?:this|selected)\s+(?:source|document)\b',question,re.I) and selected and not re.search(r'\ball\b',question,re.I): allowed &= {selected}
    return allowed,notices


def source_passages(state: Workspace,question: str,selected_source: str='',*,history=(),selected_claim='',graph_expansion=True):
    index=get_index(state)
    config=index.config if index else None
    allowed,notices=scoped_sources(state,question,selected_source)
    overview=bool(re.search(r'\b(?:summari[sz]e|overview|compare|list)\b.*\b(?:all|each|every|sources|documents)\b|^summari[sz]e[.!?]?$|do you see (?:any )?sources|how many sources|\bcompare\b.*\bversion',question,re.I))
    query=effective_query(question,history)
    chosen=[];reasons={};scores={};graph_paths=[];graph_candidates={}
    if index:
        rows=index.rows
        generic={'explain','show','tell','configure','configuration','setup','use','using','work','works','mean','means','source','sources','document','documents','please','summarize','summarise','compare','best','guess','version','versions'}
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        lexical_input=re.sub(r'\blog[ -]+in\b','login',query.casefold())
        content=[word for word in re.findall(r'\w[\w.-]*',lexical_input) if word not in generic and word not in ENGLISH_STOP_WORDS]
        lexical_query=' '.join(content) if content else query
        if not content or set(content)<={'remain','remaining','left','count','total'}:
            overview=True
        try:
            if config:
                full_query,subject_query=semantic.encode([query[:2400],lexical_query[:2400]],config)
                qvec=normalize((.7*subject_query+.3*full_query).reshape(1,-1))[0]
            else:
                qvec=normalize(index.projector.transform(index.vectorizer.transform([lexical_query])))[0]
        except semantic.SemanticUnavailable as exc:
            # Rebuild all channels together. Never mix embedding spaces after a failure.
            key=json.dumps([s.model_dump() for s in state.sources],ensure_ascii=False,sort_keys=True)
            index=build_index(key,None,str(exc));rows=index.rows;config=None
            qvec=normalize(index.projector.transform(index.vectorizer.transform([lexical_query])))[0]
        q=index.vectorizer.transform([lexical_query])
        lexical=(index.matrix@q.T).toarray().ravel()+.25*(index.metadata@q.T).toarray().ravel()
        dense=index.vectors@qvec
        qentities={m.normalized for m in extract_entities(query)}
        entities=np.asarray([len(qentities & mentions) for mentions in index.entity_sets])
        expanded=set()
        words=set(re.findall(r'\w+',query.casefold()))
        for group in TERMINOLOGY:
            if words & group: expanded |= group-words
        terminology=np.asarray([len(expanded & words) for words in index.token_sets])
        valid=[i for i,r in enumerate(rows) if r.passage.source_id in allowed]
        channels=[(lexical,'lexical match',0), (dense,'semantic match' if config else 'statistical similarity',max(.25,float(dense.max())*.45) if config else .15),
                  (entities,'exact entity',0), (terminology,'terminology match',0)]
        for values,label,threshold in channels:
            ranked=sorted([i for i in valid if values[i]>threshold],key=lambda i:(-values[i],i))[:24]
            for rank,i in enumerate(ranked):
                scores[i]=scores.get(i,0)+1/(60+rank)
                reasons.setdefault(i,[]).append(label)
        # Topic and purpose are bounded preferences, never independent hard gates.
        if index.topic_vectors.size and np.linalg.norm(qvec)>0:
            similarities=index.topic_vectors@qvec
            topic=index.topic_weights@np.maximum(similarities,0)
            # Expand with at most two strongly related topic members that other channels missed.
            expansion=sorted([i for i in valid if i not in scores and topic[i]>.42 and dense[i]>(.20 if config else .12)],key=lambda i:(-topic[i],i))[:2]
            for i in expansion:
                scores[i]=.009;reasons.setdefault(i,[])
            for i in scores:
                if topic[i]>.30:
                    scores[i]+=.003*float(topic[i]);reasons[i].append('related topic')
        if config:
            intent=index.intent_vectors@full_query
        else:
            v,p,model,_,_,_,_=document_classifier()
            intent_scores=model.predict_proba(normalize(p.transform(v.transform([question]))))[0]
            intent=np.asarray([intent_scores[list(model.classes_).index(label)] for label in INTENTS])
        if max(intent,default=0)>.25:
            plausible=[i for i in np.argsort(intent)[::-1][:2] if intent[i]>=max(intent)-.07]
            for i in scores:
                alignment=0
                for k in plausible:
                    label=list(INTENTS)[k]
                    if label in index.purpose_model.classes_:
                        j=list(index.purpose_model.classes_).index(label)
                        alignment=max(alignment,float(index.purpose_vectors[i,j]))
                if alignment>.35:
                    scores[i]+=.003*alignment;reasons[i].append('purpose match')
        if selected_source:
            relevant=[i for i in valid if rows[i].passage.source_id==selected_source and (i in scores or overview)]
            for i in relevant:
                scores[i]=scores.get(i,0)+.003;reasons.setdefault(i,[]).append('selected source')
        selected = next((c for c in state.claims if c.id==selected_claim),None)
        deictic = bool(re.search(r'\b(?:this|selected)\b|what does .* mean|\bconflict',question,re.I))
        if deictic and selected and selected.source_id in allowed:
            matching=[i for i in valid if rows[i].passage.source_id==selected.source_id and rows[i].passage.start<=selected.start<rows[i].passage.end]
            for i in matching[:1]:
                scores[i]=scores.get(i,0)+1;reasons.setdefault(i,[]).append('selected source')
        elif deictic and selected_source:
            for i in [i for i in valid if rows[i].passage.source_id==selected_source][:1]:
                scores[i]=scores.get(i,0)+.05;reasons.setdefault(i,[]).append('selected source')
        order=sorted(scores,key=lambda i:(-scores[i],i))
        if overview:
            order=[]
            # One representative per source before filling remaining slots.
            source_order=sorted(allowed,key=lambda sid:(sid!=selected_source,next((j for j,s in enumerate(state.sources) if s.id==sid),0)))
            for sid in source_order:
                candidates=[i for i in valid if rows[i].passage.source_id==sid]
                if candidates:
                    i=max(candidates,key=lambda i:(scores.get(i,0),-i));order.append(i);reasons.setdefault(i,[]).append('source overview')
            order += [i for i in valid if i not in order]
            for i in order: reasons.setdefault(i,[]).append('source overview') if 'source overview' not in reasons.get(i,[]) else None
        if not order and allowed and (allowed != {s.id for s in state.sources} or re.search(r'\b(?:highest|latest|newest)\s+version|\bonly\b|^use\s+version',question,re.I)):
            order=valid
            overview=True
            for i in order: reasons[i]=['source overview']
        # Explicitly selected summaries can focus on their document; ambient selection cannot fill the budget.
        if not order and len(allowed)==1 and re.search(r'\bsummari[sz]e\b',question,re.I):
            order=valid
            for i in order: reasons[i]=['source overview']
        if graph_expansion and not overview and order:
            # Preserve the four leading hybrid candidates; graph additions only
            # compete with lower-ranked context, and cannot cross explicit scope.
            expansions=retrieval_graph.expand(index.graph,rows,order,allowed,lexical,dense,index.vectors,bool(config))
            for target,seed,via,relation in expansions:
                graph_candidates[target]=(seed,via,relation)
                reasons.setdefault(target,[]).append('graph connection')
            added=list(graph_candidates)
            order=order[:4]+added+[i for i in order[4:] if i not in graph_candidates]
        from .nlp import source_digest
        ready=bool(state.analysis and state.analysis.source_digest==source_digest(state))
        claims={c.id:c for c in state.claims} if ready else {}
        def partners(p):
            found={c.id for c in claims.values() if c.source_id==p.source_id and c.start<p.end and c.end>p.start and c.conflicts}
            pending=list(found)
            while pending:
                c=claims[pending.pop()]
                for ident in c.conflicts:
                    if ident not in found: found.add(ident);pending.append(ident)
            return [claims[ident] for ident in sorted(found)]
        for i in order:
            candidate=rows[i].passage
            if i in graph_candidates and not any(p.id==rows[graph_candidates[i][0]].passage.id for p in chosen):
                continue
            if len(chosen)>=MAX_PASSAGES: break
            if any(p.source_id==candidate.source_id and max(0,min(p.end,candidate.end)-max(p.start,candidate.start))>=.65*min(p.end-p.start,candidate.end-candidate.start) for p in chosen): continue
            group=[(candidate,reasons.get(i,['source overview']))]
            for c in partners(candidate):
                if c.source_id not in allowed: continue
                existing=[p for p in chosen+[p for p,_ in group] if p.source_id==c.source_id and p.start<=c.start and p.end>=min(c.end,c.start+PASSAGE_SIZE)]
                if not existing:
                    source=next(s for s in state.sources if s.id==c.source_id)
                    stop=min(c.end,c.start+PASSAGE_SIZE)
                    p=SourcePassage(id=f'p-{source.id}-{c.start}-{stop}',source_id=source.id,sha256=source.sha256,start=c.start,end=stop,quote=source.text[c.start:stop])
                    group.append((p,['conflict partner']))
            group=[(p,why) for p,why in group if not any(old.id==p.id for old in chosen)]
            if len(chosen)+len(group)>MAX_PASSAGES or sum(len(p.quote) for p in chosen)+sum(len(p.quote) for p,_ in group)>MAX_SOURCE_TEXT:
                continue
            for p,why in group:
                chosen.append(p);reasons[p.id]=list(dict.fromkeys(why))[:8]
    if index and not index.topic_vectors.size:
        notices.append('No stable topic model was available for this corpus; the other retrieval channels remain active.')
    unique={p.id:p for p in chosen}
    chosen=list(unique.values())[:MAX_PASSAGES]
    covered={p.source_id for p in chosen}
    # Coverage is about actual original text, including headings not quoted as passages.
    def fully_covered(s):
        end=0
        for p in sorted((p for p in chosen if p.source_id==s.id),key=lambda p:p.start):
            if s.text[end:p.start].strip(): return False
            end=max(end,p.end)
        return not s.text[end:].strip()
    partial=any(not fully_covered(s) for s in state.sources)
    report=RetrievalReport(encoder='neural-minilm' if config else 'statistical-lsa',mode='overview' if overview else 'focused',
        model='sentence-transformers/all-MiniLM-L6-v2@'+config[2][:12] if config else 'local TF-IDF / LSA',
        included_sources=len(covered),total_sources=len(state.sources),candidate_count=len(index.rows) if index else 0,
        partial=partial,fallback=index.fallback if index else '',notices=notices,
        passages=[RetrievedPassage(**p.model_dump(),reasons=reasons.get(p.id,['source overview'])) for p in chosen])
    selected_ids={p.id for p in chosen}
    for target,(seed,via,relation) in graph_candidates.items():
        if rows[target].passage.id in selected_ids and rows[seed].passage.id in selected_ids:
            graph_paths.append(GraphPath(from_passage=rows[seed].passage.id,to_passage=rows[target].passage.id,via=via,relation=relation))
    report.graph_paths=graph_paths
    if index and chosen:
        sources={s.id:s for s in state.sources}
        selected_rows=[Candidate(p,'','paragraph',sources[p.source_id].title) for p in chosen]
        report.connections=[GraphPath(**path) for path in retrieval_graph.selected_connections(selected_rows,index.rows,index.vectors,bool(config),graph_paths,reference_graph=index.graph)]
    coverage={'included_sources':len(covered),'total_sources':len(state.sources),'partial':partial,
              'method':'hybrid passage retrieval','retrieval':report.model_dump()}
    return [p.model_dump() for p in chosen],coverage
