"""Synthetic image smoke-test payload: no broker, credentials or network calls."""
import os
from pathlib import Path
import stat

import requests
import yaml


assert os.getuid() == 10001
assert os.getgid() == 10001
for name in ('/app', '/app/entrypoint.sh', '/app/requirements.txt'):
    info = Path(name).stat()
    assert info.st_uid == 0
    assert not os.access(name, os.W_OK)
    assert not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
assert requests.__version__
assert yaml.__version__
print('Synthetic read-only sync passed', flush=True)
