"""Real loopback HTTP progress check using synthetic sources and held mock generation."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
import uvicorn
import backend.app as module
from backend import semantic
from backend.assistant import AssistantReply
from backend.providers import ProviderConfig
from tools.graph_retrieval_probe import corpus


async def main():
    release=asyncio.Event()
    captured=[]
    async def mock_generate(config,state,data,*,context):
        captured.append(context)
        await release.wait()
        return AssistantReply(answer='Synthetic held answer.',retrieval=context['retrieval'])
    with tempfile.TemporaryDirectory(prefix='atlas-graph-stream-') as directory:
        listener=socket.socket()
        listener.bind(('127.0.0.1',0))
        listener.listen()
        port=listener.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        app=module.create_app(Path(directory),auth_enabled=False,origins=[origin],provider=ProviderConfig(kind='compatible',model='mock'))
        state=app.state.store.save(corpus(),0,'Synthetic tester','Synthetic sources')
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',timeout_graceful_shutdown=2))
        with patch.object(module,'assist',mock_generate),patch.object(semantic,'configuration',return_value=(None,'Statistical integration encoder.')):
            task=asyncio.create_task(server.serve(sockets=[listener]))
            try:
                for _ in range(100):
                    if server.started: break
                    await asyncio.sleep(.02)
                if not server.started: raise RuntimeError('Local test server did not start')
                async with httpx.AsyncClient(timeout=10) as client:
                    async with client.stream('POST',origin+'/api/assistant',headers={'Origin':origin,'Accept':'application/x-ndjson'},json={'revision':state.revision,'page':'Graph','message':'How do I make a backend and frontend?'}) as response:
                        response.raise_for_status()
                        lines=response.aiter_lines()
                        first=json.loads(await asyncio.wait_for(anext(lines),5))
                        assert first['type']=='retrieval' and first['retrieval']['graph_paths'][0]['via']=='jinja'
                        assert not release.is_set()
                        release.set()
                        final=json.loads(await asyncio.wait_for(anext(lines),5))
                        assert final['type']=='answer' and final['data']['retrieval']==first['retrieval']==captured[0]['retrieval']
                assert app.state.store.read()==state
                result={'result':'PASS','transport':'real loopback HTTP with held mock generation','retrieval_received_before_model_released':True,'exact_progress_and_answer_context':True,'graph_bridge':'jinja','saved_user_workspaces_accessed':False,'synthetic_workspace_unchanged':True,'generation_api_calls':0,'browser_tested':False}
                (ROOT/'validation/graph-stream-results.json').write_text(json.dumps(result,indent=2)+'\n')
                print(json.dumps(result))
            finally:
                release.set()
                server.should_exit=True
                await asyncio.wait_for(task,5)
                listener.close()


if __name__=='__main__': asyncio.run(main())
