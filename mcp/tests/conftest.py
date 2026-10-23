"""Shared check for the network pages: every inline script must parse (a quote escaped twice in a Python string has
broken a page before). Skipped without node."""
import re
import shutil
import subprocess

import pytest

_CHECK = r"""const fs = require('fs'); const s = fs.readFileSync(process.argv[1], 'utf8'); let n = 0;
for (const m of s.matchAll(/<script>([\s\S]*?)<\/script>/g)) { new Function(m[1]); n++; }
if (!n) throw new Error('no inline script'); console.log(n);"""


@pytest.fixture()
def scripts_parse():
    def check(path) -> None:
        if not shutil.which("node"):
            pytest.skip("needs node")
        r = subprocess.run(["node", "-e", _CHECK, str(path)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]
    return check
