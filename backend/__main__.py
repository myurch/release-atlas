import os
from pathlib import Path

import uvicorn
from .app import ROOT, create_app

if __name__ == '__main__':
    app = create_app()
    host = os.getenv('ATLAS_HOST', '127.0.0.1')
    port = int(os.getenv('ATLAS_PORT', '8765'))
    print(f'Release Atlas: http://{host}:{port}')
    print('Workspace access code file: '+str(Path(os.getenv('ATLAS_DATA_DIR',ROOT/'.atlas'))/'access-code'))
    print('One worker. Remote access requires configured origins and HTTPS. Read README.md.')
    uvicorn.run(app,host=host,port=port,workers=1)
