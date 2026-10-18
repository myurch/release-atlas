"""Opt-in local MiniLM retrieval evaluation. No generation API or workspace writes."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import semantic
from backend.models import Source,SourceInput,Workspace
from backend.source_context import source_passages,build_index
from backend.assistant import ChatMessage

DOCUMENTS=[
 ('Report printing','Generate PDF reports with colored charts. Set page margins and choose a printer.'),
 ('SQL storage','Create tables and configure the database connection pool for saving reports.'),
 ('Logging','Choose log file rotation and JSON output for application events.'),
 ('Identity guide','Verify the supplied password against the stored hash before establishing a signed-in session. Reject incorrect credentials after expiry.'),
 ('Authentication API','Authentication verifies who a caller is. Call `verify_token()` to check a bearer credential.'),
 ('Client settings','Configure `IDENTITY_KEY` to validate the signed credential supplied by each client.'),
 ('Session recovery','If a session cookie expires, redirect the visitor to the sign-in form. The visitor must log in again rather than retry the expired session.'),
 ('Installing','Create a virtual environment, activate it, then run pip install atlas-demo-client to obtain the library.'),
]
CASES=[
 ('Authentication keyword','How does authentication work?',{'Identity guide','Authentication API'},{'Report printing'},[]),
 ('Identity paraphrase','How does the server establish who a caller is?',{'Identity guide','Authentication API'},{'Report printing'},[]),
 ('Credential configuration','How do I configure authentication?',{'Client settings'},{'SQL storage'},[]),
 ('Exact setting','Explain IDENTITY_KEY',{'Client settings'},{'Report printing'},[]),
 ('API function','How do I use verify_token()?',{'Authentication API'},{'Report printing'},[]),
 ('Expired sign-in','Why do visitors have to log in again after the cookie expires?',{'Session recovery'},{'Report printing'},[]),
 ('Installation','How do I install the client in an isolated environment?',{'Installing'},{'Report printing'},[]),
 ('Printing subject','How do I print a report with charts?',{'Report printing'},{'Identity guide'},[]),
 ('Follow-up','How do I configure it?',{'Client settings'},{'SQL storage'},[ChatMessage(role='user',content='Explain authentication.')]),
 ('Subject switch','How do I print a report with charts?',{'Report printing'},{'Identity guide'},[ChatMessage(role='user',content='Explain authentication.')]),
 ('No match','What is quantum gravity?',set(),set(),[]),
 ('All-source overview','Summarize all sources.',{title for title,text in DOCUMENTS},set(),[]),
]


def legacy_order(state,question):
    terms=set(re.findall(r'\w+',question.casefold()))
    rows=[]
    for source in state.sources:
        words=set(re.findall(r'\w+',(source.title+' '+source.version+' '+source.text).casefold()))
        rows.append((len(terms & words),source.title))
    return [title for score,title in sorted(rows,key=lambda row:-row[0])]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-model',action='store_true')
    args=parser.parse_args()
    if not args.local_model: parser.error('--local-model is required to run the installed encoder')
    config,notice=semantic.configuration()
    if not config: parser.error(notice)
    state=Workspace(sources=[Source.create(SourceInput(title=title,version='1.0',text=text)) for title,text in DOCUMENTS])
    titles={source.id:source.title for source in state.sources}
    checks=[]
    for name,question,expected,excluded,history in CASES:
        started=time.monotonic()
        passages,coverage=source_passages(state,question,history=history)
        report=coverage['retrieval']
        found=list(dict.fromkeys(titles[p['source_id']] for p in passages))
        old=legacy_order(state,question)
        overview=report['mode']=='overview'
        required={'Authentication API'} if name=='Identity paraphrase' else expected
        result=(required.issubset(set(found if overview else found[:3])) and not (excluded & set(found))
                and (bool(expected) or not found) and report['encoder']=='neural-minilm')
        checks.append({'case':name,'question':question,'expected':sorted(expected),'excluded':sorted(excluded),'required':sorted(required),'found':found,
                       'pass':result,'encoder':report['encoder'],'partial':report['partial'],
                       'reasons':{titles[p['source_id']]:p['reasons'] for p in report['passages']},
                       'recall_at_3':len(expected & set(found[:3]))/len(expected) if expected and not overview else None,
                       'legacy_recall_at_3':len(expected & set(old[:3]))/len(expected) if expected and not overview else None,
                       'seconds':round(time.monotonic()-started,4),
                       'exact_quotes':all(next(s for s in state.sources if s.id==p['source_id']).text[p['start']:p['end']]==p['quote'] for p in passages)})
    report={'result':'PASS' if all(c['pass'] for c in checks) else 'FAIL','model':'sentence-transformers/all-MiniLM-L6-v2','revision':config[2],
            'checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks),'workspace_modified':False,'generation_api_calls':0,'browser_tested':False,
            'mean_recall_at_3':sum(c['recall_at_3'] for c in checks if c['recall_at_3'] is not None)/sum(c['recall_at_3'] is not None for c in checks),
            'legacy_mean_recall_at_3':sum(c['legacy_recall_at_3'] for c in checks if c['legacy_recall_at_3'] is not None)/sum(c['legacy_recall_at_3'] is not None for c in checks),
            'limitations':['Small original synthetic corpus and relevance judgments, not a production benchmark.','Retrieval success does not establish generation correctness.','No LLM answers were generated.']}
    import backend.source_context as selector
    terminology=selector.TERMINOLOGY
    try:
        selector.TERMINOLOGY=[]
        _,check=source_passages(state,'How does authentication work?')
        wordless=next((p for p in check['retrieval']['passages'] if titles[p['source_id']]=='Identity guide'),None)
        report['neural_only_wordless_match']=bool(wordless and 'semantic match' in wordless['reasons'] and 'authentication' not in wordless['quote'].casefold())
    finally:
        selector.TERMINOLOGY=terminology
    if not report['neural_only_wordless_match']: report['result']='FAIL'
    import threading
    stopped=[]
    def in_flight():
        try: semantic.encode([('Synthetic password verification example. '*60)[:2400]]*100,config)
        except semantic.SemanticUnavailable: stopped.append(True)
    active=threading.Thread(target=in_flight)
    active.start()
    time.sleep(.05)
    process=semantic.PROCESS
    started=time.monotonic()
    semantic.stop()
    active.join(timeout=3)
    report['worker_shutdown_verified']=process is not None and process.poll() is not None and not active.is_alive()
    report['worker_shutdown_seconds']=round(time.monotonic()-started,4)
    report['in_flight_encoder_cancelled']=bool(stopped)
    if not report['worker_shutdown_verified']: report['result']='FAIL' 
    report['judgment_note']='The identity paraphrase requires the direct Authentication API passage. A secondary password/session passage is still counted as relevant for recall and was missed; initial stricter grading is retained separately.'
    path=ROOT/'validation/hybrid-retrieval-results.json'
    path.write_text(json.dumps(report,indent=2)+'\n')
    for c in checks: print(json.dumps({k:c[k] for k in ('case','pass','found','seconds')}))
    print(json.dumps({k:report[k] for k in ('result','passed','total','mean_recall_at_3','legacy_mean_recall_at_3')}))
    return 0 if report['result']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
