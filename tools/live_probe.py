"""Optional real local provider checks with non-sensitive synthetic evidence."""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.models import Workspace
from backend.nlp import retrieve
from backend.providers import ProviderConfig, generate

async def main():
    state=Workspace.model_validate_json((ROOT/'data/demo-snapshot.json').read_text())
    evidence=retrieve(state,'What affects Checkout service?', 'graph')
    results=[]
    for kind,base in [('ollama','http://localhost:11434'),('compatible','http://localhost:11434/v1')]:
        start=time.monotonic()
        answer=await generate(ProviderConfig(kind=kind,base=base),'Do the sources agree about retry_limit in 2.0? Explain only what the evidence supports.',evidence)
        assert set(answer.citations).issubset({r['claim']['id'] for r in evidence})
        results.append({'kind':kind,'base':base,'model':'gpt-oss:20b','elapsed_seconds':round(time.monotonic()-start,3),'answer':answer.model_dump(),'citation_allowlist':'PASS','scope':'Actual generation, not a mock; semantic grounding still needs human review'})
    (ROOT/'validation/live-provider-results.json').write_text(json.dumps({'result':'PASS','runs':results,'limitations':['One small synthetic question per adapter is not a quality or latency benchmark','Remote paid providers and external embedding models not tested']},indent=2)+'\n')
    print(json.dumps(results,indent=2))

asyncio.run(main())
