#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import textwrap

SOURCE_COMMIT = "645017a9c8773f207428a39d42d8d763a92f4c29"
PATH = ".github/workflows/i009-closure-migration.yml"
raw = subprocess.check_output(["git", "show", f"{SOURCE_COMMIT}:{PATH}"], text=True)
marker = "          python3 - <<'PY'\n"
end = "\n          PY\n"
assert raw.count(marker) == 1
body = raw.split(marker, 1)[1].split(end, 1)[0]
code = textwrap.dedent(body)
compile(code, "i009-closure-migration-extracted", "exec")
exec(code, {"__name__": "__main__"})
