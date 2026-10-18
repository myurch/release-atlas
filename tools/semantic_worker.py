"""Offline MiniLM ONNX worker. Private JSON pipes, no server credentials or network."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

folder=Path(__file__).resolve().parents[1]/'.tools/semantic/model'
manifest=json.loads((folder/'manifest.json').read_text())
if manifest.get('model')!='sentence-transformers/all-MiniLM-L6-v2':
    raise ValueError('Unexpected local model')
for name in ('model.onnx','tokenizer.json'):
    if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=manifest['files'][name]:
        raise ValueError('Local model integrity check failed')
tokenizer=Tokenizer.from_file(str(folder/'tokenizer.json'))
tokenizer.enable_truncation(max_length=256,stride=32)
tokenizer.enable_padding(length=256)
options=ort.SessionOptions()
options.intra_op_num_threads=2
options.inter_op_num_threads=1
session=ort.InferenceSession(str(folder/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
inputs={row.name for row in session.get_inputs()}
for line in sys.stdin:
    try:
        if len(line.encode())>3_000_000: raise ValueError('Input limit')
        request=json.loads(line)
        texts=request['texts']
        if not isinstance(texts,list) or not 1<=len(texts)<=1000 or any(not isinstance(t,str) or len(t)>2600 for t in texts):
            raise ValueError('Input bounds')
        vectors=[]
        chunks=[]
        owners=[]
        for owner,text in enumerate(texts):
            encoded=tokenizer.encode(text)
            pieces=[encoded]+encoded.overflowing
            if len(pieces)>16: raise ValueError('Token window limit')
            chunks.extend(pieces)
            owners.extend([owner]*len(pieces))
        totals=np.zeros((len(texts),384),dtype=float)
        counts=np.zeros((len(texts),1),dtype=float)
        for start in range(0,len(chunks),16):
            encoded=chunks[start:start+16]
            feed={'input_ids':np.asarray([e.ids for e in encoded],dtype=np.int64),
                  'attention_mask':np.asarray([e.attention_mask for e in encoded],dtype=np.int64),
                  'token_type_ids':np.asarray([e.type_ids for e in encoded],dtype=np.int64)}
            output=session.run(None,{k:v for k,v in feed.items() if k in inputs})[0]
            mask=feed['attention_mask'][:,:,None]
            pooled=(output*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1)
            pooled/=np.maximum(np.linalg.norm(pooled,axis=1,keepdims=True),1e-12)
            for j,vector in enumerate(pooled):
                owner=owners[start+j]
                weight=float(mask[j].sum())
                totals[owner]+=vector*weight
                counts[owner]+=weight
        totals/=np.maximum(counts,1)
        totals/=np.maximum(np.linalg.norm(totals,axis=1,keepdims=True),1e-12)
        vectors=totals.tolist()
        print(json.dumps({'vectors':vectors,'model':manifest['model'],'revision':manifest['revision']}),flush=True)
    except Exception:
        print(json.dumps({'error':'Local semantic encoder could not process this bounded request.'}),flush=True)
