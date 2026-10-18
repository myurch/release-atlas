"""Local NLP evaluation and optional inspection of a user-approved public README.

No model/network requests or user workspace changes. Report metadata, not source text.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.document_classifier import document_evaluation
from backend.models import Source,SourceInput,Workspace
from backend.nlp import analyze


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-file',type=Path)
    args=parser.parse_args()
    report={
        'classification':document_evaluation(),
        'limitations':[
            'Original synthetic training/evaluation share an author and domain; this is not a production accuracy estimate.',
            'LSA is a statistical embedding baseline, not a pretrained neural embedding model.',
            'Nearest training examples explain similarity, not causal feature attribution.',
            'NMF topics and syntax-based entity types require human inspection.',
        ],
        'browser_tested':False,'workspace_modified':False,'model_api_calls':0,
    }
    if args.reference_file:
        text=args.reference_file.read_text()
        source=Source.create(SourceInput(title='Public reference README',version='reference',text=text))
        state=analyze(Workspace(sources=[source]))
        report['reference']={
            'source_hash':source.sha256,'characters':len(text),'pipeline':state.analysis.pipeline.model_dump(),
            'sections':list(dict.fromkeys(' > '.join(c.document.headings) for c in state.claims)),
            'purposes':{p:sum(c.document.purpose==p for c in state.claims) for p in sorted({c.document.purpose for c in state.claims})},
            'entity_types':{k:len({m.normalized for c in state.claims for m in c.document.mentions if m.kind==k}) for k in sorted({m.kind for c in state.claims for m in c.document.mentions})},
            'exact_passages':all(text[c.start:c.end]==c.quote for c in state.claims),
            'exact_mentions':all(text[m.start:m.end]==m.name for c in state.claims for m in c.document.mentions),
            'topics':[{'terms':t.terms,'passages':t.count,'sources':t.source_count} for t in state.topics],
        }
    path=ROOT/'validation/documentation-evaluation.json'
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'macro_f1':report['classification']['macro_f1'],'keyword_macro_f1':report['classification']['keyword_macro_f1'],
                      'reference':report.get('reference',{}),'report':str(path)}))


if __name__=='__main__':
    main()
