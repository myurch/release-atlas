import os
from pathlib import Path

import uvicorn
from .app import ROOT, create_app
from .config import load_env
from .semantic import stop as stop_semantic


class AtlasServer(uvicorn.Server):
    async def shutdown(self, sockets=None):
        stop_semantic()
        # SSE streams otherwise keep Uvicorn waiting indefinitely for completion.
        for queue in tuple(self.config.app.state.listeners):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(None)
        await super().shutdown(sockets)


if __name__ == '__main__':
    try:
        load_env()
    except (OSError, UnicodeError, ValueError):
        raise SystemExit('Cannot load .env. Check file permissions and single-line ATLAS_* or OPENAI_API_KEY assignments.') from None
    app = create_app()
    host = os.getenv('ATLAS_HOST', '127.0.0.1')
    port = int(os.getenv('ATLAS_PORT', '8765'))
    print(f'Release Atlas: http://{host}:{port}')
    if app.state.auth_enabled:
        print('Workspace access code file: '+str(Path(os.getenv('ATLAS_DATA_DIR',ROOT/'.atlas'))/'access-code'))
    else:
        print('Sign-in disabled. Set ATLAS_AUTH_ENABLED=1 to require an access code.')
    print('One worker. Remote access requires configured origins and HTTPS. Read README.md.')
    try:
        AtlasServer(uvicorn.Config(app,host=host,port=port,workers=1,timeout_graceful_shutdown=5)).run()
    except KeyboardInterrupt:
        pass
