"""Download only pinned public model artifacts for the local ONNX encoder."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
MODEL='sentence-transformers/all-MiniLM-L6-v2'
revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
ARTIFACTS={'onnx/model.onnx': '6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452', 'tokenizer.json': 'be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037'}
folder=ROOT/'.tools/semantic/model'
folder.mkdir(parents=True,exist_ok=True)
files={}
for name,expected in ARTIFACTS.items():
    target=folder/Path(name).name
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:
        files[target.name]=expected
        continue
    url='https://huggingface.co/'+MODEL+'/resolve/'+revision+'/'+name
    with urllib.request.urlopen(url,timeout=60) as response, target.with_suffix(target.suffix+'.part').open('wb') as output:
        total=0
        while chunk:=response.read(1024*1024):
            total+=len(chunk)
            if total>150_000_000:
                raise ValueError('Model artifact exceeds download limit')
            output.write(chunk)
    target.with_suffix(target.suffix+'.part').replace(target)
    files[target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
    if files[target.name]!=expected:
        target.unlink()
        raise ValueError('Model artifact hash mismatch')
with urllib.request.urlopen('https://www.apache.org/licenses/LICENSE-2.0.txt',timeout=30) as response:
    (folder/'LICENSE.txt').write_bytes(response.read(30000))
manifest={'model':MODEL,'revision':revision,'files':files,'dimensions':384,'max_tokens':256,'license':'Apache-2.0'}
(folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
