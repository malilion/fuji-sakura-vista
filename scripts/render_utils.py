"""Bound Blender's native render output and keep the full log on disk."""
import contextlib
import ctypes
import os
import sys
from pathlib import Path


@contextlib.contextmanager
def render_log(path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    sys.stdout.flush(); sys.stderr.flush()
    original_out=os.dup(1); original_err=os.dup(2)
    with path.open('w') as log:
        try:
            os.dup2(log.fileno(),1); os.dup2(log.fileno(),2)
            yield
        finally:
            sys.stdout.flush(); sys.stderr.flush()
            ctypes.CDLL(None).fflush(None)
            os.dup2(original_out,1); os.dup2(original_err,2)
            os.close(original_out); os.close(original_err)
    print('\n'.join(path.read_text(errors='replace').splitlines()[-9:]),flush=True)
