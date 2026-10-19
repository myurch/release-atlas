"""Compare hybrid and graph-augmented retrieval on synthetic saved text only."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import semantic
from backend.models import Source,SourceInput,Workspace
from backend.source_context import source_passages,build_index
from tools.retrieval_probe import CASES,DOCUMENTS


def corpus():
    flask='\n\n'.join(f'# Web flow {i}\n\nFlask connects a backend and frontend by rendering HTML templates with Jinja. The server sends rendered markup to the browser. Route {i} returns a template response.' for i in range(10))
    documents=[('pallets/flask README',flask),('pallets/jinja README','# Template inheritance\n\nTemplates generate HTML markup from variables. Reuse page structure with inheritance and blocks. Escape variable output when rendering templates.'),('Garden notes','Plant apples in spring and water the trees.')]
    return Workspace(sources=[Source.create(SourceInput(title=t,text=x,version='1.0')) for t,x in documents])


def compare(state,question,**kwargs):
    baseline,_=source_passages(state,question,graph_expansion=False,**kwargs)
    expanded,coverage=source_passages(state,question,**kwargs)
    titles={s.id:s.title for s in state.sources}
    return {'baseline':[titles[p['source_id']] for p in baseline],
            'expanded':[titles[p['source_id']] for p in expanded],
            'first_four_preserved':expanded[:4]==baseline[:4],
            'graph_paths':coverage['retrieval']['graph_paths'],
            'connections':coverage['retrieval']['connections'],
            'encoder':coverage['retrieval']['encoder'],
            'within_budget':len(expanded)<=8 and sum(len(p['quote']) for p in expanded)<=16000,
            'exact_quotes':all(next(s for s in state.sources if s.id==p['source_id']).text[p['start']:p['end']]==p['quote'] for p in expanded),
            'unchanged':baseline==expanded}


def evaluate():
    web=compare(corpus(),'How do I make a backend and frontend?')
    web['pass']=('pallets/jinja README' not in web['baseline'] and 'pallets/jinja README' in web['expanded'] and 'Garden notes' not in web['expanded'] and web['first_four_preserved'] and web['within_budget'] and web['exact_quotes'] and len(web['graph_paths'])==1)
    short=Workspace(sources=[Source.create(SourceInput(title=t,text=x,version='1.0')) for t,x in [
        ('Flask documentation','Flask handles backend requests and sends HTML templates to Jinja for rendering.'),
        ('Jinja documentation','HTML templates render variables and reuse page layouts through inheritance.')]])
    direct=compare(short,'How do HTML templates work?')
    direct['pass']=direct['unchanged'] and not direct['graph_paths'] and any(p['via']=='jinja' for p in direct['connections']) and set(direct['expanded'])=={'Flask documentation','Jinja documentation'}
    state=Workspace(sources=[Source.create(SourceInput(title=t,text=x,version='1.0')) for t,x in DOCUMENTS])
    checks=[]
    for name,question,expected,excluded,history in CASES:
        result=compare(state,question,history=history)
        result.update(case=name,pass_=result['unchanged'] and result['within_budget'] and result['exact_quotes'])
        checks.append(result)
    return {'web_case':web,'direct_selection_case':direct,'existing_cases':checks,'pass':web['pass'] and direct['pass'] and all(c['pass_'] for c in checks)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-model',action='store_true',help='Also test the installed offline MiniLM worker; no generation API calls.')
    args=parser.parse_args()
    report={'generation_api_calls':0,'saved_workspaces_accessed':False,'browser_tested':False,
            'limitations':['Original synthetic fixtures only; not a production accuracy benchmark.','No generated answers evaluated.','Technology identities use distinctive leading source titles or owner/repository names; ambiguous names are skipped.']}
    with patch.object(semantic,'configuration',return_value=(None,'Statistical mode selected for synthetic testing.')):
        build_index.cache_clear()
        report['statistical']=evaluate()
    if args.local_model:
        build_index.cache_clear()
        config,notice=semantic.configuration()
        if not config: raise SystemExit(notice)
        report['model_revision']=config[2]
        report['neural']=evaluate()
    semantic.shutdown()
    report['result']='PASS' if all(report[k]['pass'] for k in ('statistical','neural') if k in report) else 'FAIL'
    (ROOT/'validation/graph-retrieval-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'result':report['result'],'modes':{k:{'web_case':report[k]['web_case']['pass'],'direct_selection_connections':report[k]['direct_selection_case']['pass'],'unchanged_existing_cases':sum(c['unchanged'] for c in report[k]['existing_cases']),'total_existing_cases':len(report[k]['existing_cases'])} for k in ('statistical','neural') if k in report},'generation_api_calls':0}))
    if report['result']!='PASS': raise SystemExit(1)


if __name__=='__main__': main()
