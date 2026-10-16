"""Synthetic image smoke-test payload: no broker, credentials or network calls.

The container check mounts this file over the installed package's __main__.py,
so the entrypoint's `python -m ghostfolio_ibkr_sync` runs it as the program.
"""
import importlib.util
import os
import stat
import sys
from pathlib import Path

import requests
import yaml


assert os.getuid() == 10001
assert os.getgid() == 10001
assert sys.orig_argv[-2:] == ['-m', 'ghostfolio_ibkr_sync'], sys.orig_argv
assert __package__ == 'ghostfolio_ibkr_sync'
assert 'site-packages' in Path(__file__).parts
spec = importlib.util.find_spec('ghostfolio_ibkr_sync')
assert spec is not None and spec.origin is not None
package = Path(spec.origin).parent
assert not list(Path('/app').glob('*.py')), 'no source file may ship in /app'
# This file is the bind-mounted probe: it keeps the host owner, the rest is the image's.
installed = [path for path in package.glob('*.py') if path != Path(__file__)]
assert len(installed) >= 9, installed
for name in ('/app', '/app/entrypoint.sh', '/app/requirements.txt', package, *installed):
    info = Path(name).stat()
    assert info.st_uid == 0
    assert not os.access(name, os.W_OK)
    assert not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
assert requests.__version__
assert yaml.__version__
print('Synthetic read-only sync passed', flush=True)
