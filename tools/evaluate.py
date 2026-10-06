"""Reproducible small-corpus evidence. Scores are not production accuracy claims."""
import json
import re
import sys
from pathlib import Path

from sklearn.metrics import classification_report, f1_score

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.models import Source, SourceInput, Usage, Workspace
from backend.nlp import analyze, classify, entities, retrieve

examples=json.loads((ROOT/'data/evaluation.json').read_text())['examples']
train=json.loads((ROOT/'data/training.json').read_text())['examples']
assert not set(t for _,t in examples).intersection(t for _,t in train)
expected=[c for c,_ in examples]
predicted=[c for c,_ in classify([t for _,t in examples])]
def baseline(text):
    words={'breaking':r'removed|incompatible|no longer supported','deprecation':r'deprecat|scheduled.*removal|removal.*scheduled','security':r'security|vulnerab|injection|credentials','feature':r'added|introduced|new','fix':r'fixed|corrected|resolved'}
    return next((k for k,p in words.items() if re.search(p,text,re.I)),'other')
raw=json.loads((ROOT/'data/demo-input.json').read_text())
state=analyze(Workspace(title=raw['title'],sources=[Source.create(SourceInput(**s)) for s in raw['sources']],usage=[Usage(**u) for u in raw['usage']]))
queries=[('What affects Checkout service?','retry_limit'),('What affects Export worker?','export_batch'),('What affects Admin portal?','legacy_auth'),('What changed for retry_limit?','retry_limit')]
retrieval=[]
for question,entity in queries:
    relevant={c.id for c in state.claims if entity in c.entities}
    row={'question':question,'expected_entity':entity,'relevant_count':len(relevant)}
    for mode in ['lexical','vector','graph']:
        found={x['claim']['id'] for x in retrieve(state,question,mode,6)}
        row[mode+'_recall_at_6']=len(found&relevant)/len(relevant)
    retrieval.append(row)
entity_cases=[('Use `pool_cap` and `fetch_records`.',['fetch_records','pool_cap']),('Call fetchRecords with queue_size.',['fetchrecords','queue_size']),('No technical identifier here.',[]),('支持 `unicode_option`。',['unicode_option'])]
entity_correct=sum(entities(t)==e for t,e in entity_cases)
report={'classification':{'held_out_examples':len(examples),'training_examples':len(train),'macro_f1':f1_score(expected,predicted,average='macro'),'keyword_baseline_macro_f1':f1_score(expected,[baseline(t) for _,t in examples],average='macro'),'report':classification_report(expected,predicted,output_dict=True,zero_division=0)},'retrieval':retrieval,'entity_exact_set_accuracy':entity_correct/len(entity_cases),'quote_integrity':all(next(s for s in state.sources if s.id==c.source_id).text[c.start:c.end]==c.quote for c in state.claims),'same_version_conflict_candidates':sum(bool(c.conflicts) for c in state.claims),'limitations':['Small original synthetic corpus; no claim of representative production quality','Evaluation wording/entities are disjoint from training, but domain and author are shared','Rule-based technical entity and conflict extraction does not handle general named entities, negation or version ranges comprehensively','Graph advantage is tested on declared usage bridges; does not establish universal superiority over text retrieval','Classifier score is uncalibrated; no upgrade-safety prediction']}
assert report['classification']['macro_f1']>=.70
assert report['quote_integrity'] and entity_correct==len(entity_cases)
assert all(r['graph_recall_at_6']>0 for r in retrieval)
(ROOT/'validation/evaluation-results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'macro_f1':report['classification']['macro_f1'],'keyword_baseline_macro_f1':report['classification']['keyword_baseline_macro_f1'],'graph_recall_at_6':[x['graph_recall_at_6'] for x in retrieval],'quote_integrity':report['quote_integrity']}))
