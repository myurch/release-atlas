"""Documentation-purpose classification using normalized LSA embeddings.

A local statistical baseline, not a pretrained transformer or a risk predictor.
Nearest training examples explain vector proximity, not causal feature importance.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import normalize

from .models import ClassificationExample, PurposeScore, digest


@lru_cache(maxsize=1)
def document_classifier():
    raw = (Path(__file__).resolve().parents[1]/'data/document-training.json').read_text()
    labels, texts = zip(*json.loads(raw)['examples'])
    vectorizer = TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,strip_accents='unicode')
    matrix = vectorizer.fit_transform(texts)
    projector = TruncatedSVD(n_components=min(48,len(texts)-1,matrix.shape[1]-1),random_state=11)
    vectors = normalize(projector.fit_transform(matrix))
    model = LogisticRegression(C=8,max_iter=1000,random_state=11).fit(vectors,labels)
    return vectorizer,projector,model,vectors,labels,texts,digest(raw)


def classify_documents(texts):
    vectorizer,projector,model,training,labels,examples,_ = document_classifier()
    vectors = normalize(projector.transform(vectorizer.transform(texts)))
    predictions = model.predict_proba(vectors)
    output = []
    for vector, scores in zip(vectors,predictions):
        order = np.argsort(scores)[::-1]
        nearest = np.argsort(training @ vector)[::-1][:2]
        # Abstain when vocabulary coverage or separation is insufficient.
        supported = bool(np.linalg.norm(vector) > 0 and scores[order[0]] >= .32 and scores[order[0]]-scores[order[1]] >= .05)
        output.append({
            'purpose':str(model.classes_[order[0]]) if supported else 'other',
            'alternatives':[PurposeScore(label=str(model.classes_[i]),score=round(float(scores[i]),4)) for i in order[:3]],
            'examples':[ClassificationExample(label=labels[i],text=examples[i],similarity=round(float(np.clip(training[i] @ vector,-1,1)),4)) for i in nearest if training[i] @ vector > .05],
        })
    return output


def purpose_baseline(text):
    """Fixed keyword baseline, with explicit priority for mixed-purpose text."""
    import re
    patterns = [
        ('troubleshooting',r'troubleshoot|diagnos|if .*fail|unexpected exception'),
        ('migration',r'migrat|upgrad|deprecat|incompatib'),
        ('security',r'secur|untrusted|authoriz|secret|tls'),
        ('example',r'example|sample|tutorial'),
        ('installation',r'install|setup|prerequisit'),
        ('configuration',r'configur|settings|default|environment variable'),
        ('api-reference',r'api|attribute|method|endpoint|function reference'),
        ('resources',r'links|license|contribut|community|tracker'),
        ('overview',r'library|toolkit|features|framework'),
    ]
    return next((label for label,pattern in patterns if re.search(pattern,text,re.I)),'other')


@lru_cache(maxsize=1)
def document_evaluation():
    from sklearn.metrics import classification_report, f1_score
    raw = (Path(__file__).resolve().parents[1]/'data/document-evaluation.json').read_text()
    cases = json.loads(raw)['examples']
    expected = [label for label,_ in cases]
    predicted = [result['purpose'] for result in classify_documents([text for _,text in cases])]
    baseline = [purpose_baseline(text) for _,text in cases]
    return {'held_out_examples':len(cases),'macro_f1':round(float(f1_score(expected,predicted,average='macro')),4),
            'keyword_macro_f1':round(float(f1_score(expected,baseline,average='macro')),4),
            'evaluation_hash':digest(raw),'training_hash':document_classifier()[6],
            'per_label':classification_report(expected,predicted,output_dict=True,zero_division=0),
            'cases':[{'expected':label,'predicted':prediction,'baseline':base} for label,prediction,base in zip(expected,predicted,baseline)]}
