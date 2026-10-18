"""Bounded local semantic encoder client. No runtime downloads, URLs or credentials."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import threading
import time

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'.tools/semantic/model/manifest.json'
LOCK=threading.Lock()
STATE_LOCK=threading.Lock()
PROCESS=None
STOPPED=False


class SemanticUnavailable(Exception):
    pass


def configuration():
    if STOPPED: raise SemanticUnavailable('The semantic worker is stopping with the server.')
    mode=os.getenv('ATLAS_RETRIEVAL_ENCODER','auto')
    if mode not in ('auto','neural','statistical'):
        raise SemanticUnavailable('Invalid retrieval encoder configuration; using statistical fallback.')
    python=Path(os.getenv('ATLAS_RETRIEVAL_PYTHON',str(ROOT/'.tools/semantic/venv/bin/python')))
    if mode=='statistical':
        return None,'Statistical encoder selected in configuration.'
    if not python.is_file() or not MODEL.is_file():
        return None,'Neural encoder is not installed. Run sh install-release-atlas-semantic.sh; using the weaker statistical fallback.'
    try:
        manifest=json.loads(MODEL.read_text())
        if manifest.get('model')!='sentence-transformers/all-MiniLM-L6-v2' or len(manifest['revision'])!=40:
            raise ValueError('Manifest')
        fingerprint=hashlib.sha256(MODEL.read_bytes()).hexdigest()
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise SemanticUnavailable('Local semantic model metadata is invalid; using statistical fallback.') from exc
    return (str(python),fingerprint,manifest['revision']),''


def shutdown():
    global PROCESS
    # Take ownership once. A timeout and server shutdown may arrive together.
    with STATE_LOCK:
        proc=PROCESS
        PROCESS=None
    if proc is not None:
        try: proc.kill()
        except ProcessLookupError: pass
        try: proc.wait(timeout=2)
        except subprocess.TimeoutExpired: pass
        for stream in (proc.stdin,proc.stdout):
            if stream:
                try: stream.close()
                except (OSError,ValueError): pass


def stop():
    global STOPPED
    with STATE_LOCK:
        STOPPED=True
    shutdown()


atexit.register(shutdown)


def encode(texts,config):
    """Serialize one fixed worker request; terminate on timeout or malformed output."""
    global PROCESS
    if STOPPED: raise SemanticUnavailable('The semantic worker is stopping with the server.')
    if not texts or len(texts)>1000 or any(not isinstance(t,str) or len(t)>2600 for t in texts):
        raise SemanticUnavailable('Semantic input exceeds supported bounds; using statistical fallback.')
    payload=(json.dumps({'texts':texts},ensure_ascii=True)+'\n').encode()
    if len(payload)>3_000_000:
        raise SemanticUnavailable('Semantic input exceeds supported bounds; using statistical fallback.')
    with LOCK:
        try:
            with STATE_LOCK:
                proc=PROCESS
            if proc is None or proc.poll() is not None or getattr(proc,'atlas_config',None)!=config:
                shutdown()
                with STATE_LOCK:
                    if STOPPED: raise SemanticUnavailable('The semantic worker is stopping with the server.')
                    proc=subprocess.Popen([config[0],str(ROOT/'tools/semantic_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,env={'PATH':os.defpath,'LANG':'en_US.UTF-8','PYTHONNOUSERSITE':'1','TOKENIZERS_PARALLELISM':'false','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','VECLIB_MAXIMUM_THREADS':'2'})
                    proc.atlas_config=config
                    PROCESS=proc
            # A writer thread prevents a stalled worker from blocking the timeout.
            errors=[]
            def write():
                try:
                    proc.stdin.write(payload)
                    proc.stdin.flush()
                except (OSError,ValueError) as exc: errors.append(exc)
            writer=threading.Thread(target=write,daemon=True)
            writer.start()
            deadline=time.monotonic()+90
            data=bytearray()
            while not data.endswith(b'\n'):
                remaining=deadline-time.monotonic()
                if remaining<=0 or not select.select([proc.stdout],[],[],remaining)[0]:
                    raise ValueError('Worker timed out')
                chunk=os.read(proc.stdout.fileno(),65536)
                if not chunk or len(data)+len(chunk)>12_000_000: raise ValueError('Worker output bounds')
                data.extend(chunk)
            line=bytes(data)
            writer.join(timeout=1)
            if errors or writer.is_alive() or len(line)>12_000_000 or not line.endswith(b'\n'):
                raise ValueError('Worker output bounds')
            result=json.loads(line)
            if result.get('revision')!=config[2]: raise ValueError('Model revision mismatch')
            matrix=np.asarray(result['vectors'],dtype=float)
            if matrix.shape!=(len(texts),384) or not np.isfinite(matrix).all() or (np.linalg.norm(matrix,axis=1)<1e-8).any():
                raise ValueError('Invalid embeddings')
            return matrix/np.linalg.norm(matrix,axis=1,keepdims=True)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            shutdown()
            raise SemanticUnavailable('Local semantic encoder failed or timed out; using the weaker statistical fallback.') from exc
