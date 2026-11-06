# SYNC elapsed-credit V1 evidence

Implementation: `a64090d73dd4206fffc9f1f69d7f139e9c158996`.
The freeze and result documents are two directories above this directory.

`raw-evidence.tar.xz.b64` losslessly preserves 70 members: original diagnosis
freeze/logs/traces and logging-only scratch sources, original command arrays,
new-test before failures, default/tiny after logs and complete normal-cadence
state/reference bytes. The two equal before/after binary streams for each build
are represented by one common byte-identical stream; comparison receipts retain
both execution identities and hashes. XZ is only a transport encoding.

`manifest.json` binds the encoded container, XZ and tar bytes, every decoded
member and the full original failed GitHub job log text. `summary.json` records
the observed outcomes and exact source hashes. Original stdout/stderr bytes,
including blank lines, are inside the container and are never whitespace-cleaned.

Verify and reconstruct into a new external directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 - /new/external/sync-credit-evidence <<'PY'
import base64, hashlib, io, json, lzma, sys, tarfile
from pathlib import Path, PurePosixPath
def verify(data, record):
    assert len(data) == record['bytes']
    assert hashlib.sha256(data).hexdigest() == record['sha256']
m = json.loads(Path('manifest.json').read_text())
e = Path(m['container']['path']).read_bytes()
verify(e, m['container']['encoded'])
assert e.endswith(b'\n') and e.count(b'\n') == 1
x = base64.b64decode(e[:-1], validate=True)
verify(x, m['container']['xz'])
b = lzma.decompress(x)
verify(b, m['container']['tar'])
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=False)
with tarfile.open(fileobj=io.BytesIO(b), mode='r:') as tar:
    assert set(tar.getnames()) == set(m['members'])
    for member in tar.getmembers():
        name = PurePosixPath(member.name)
        assert member.isfile() and not name.is_absolute() and '..' not in name.parts
        data = tar.extractfile(member).read()
        verify(data, m['members'][member.name])
        path = out / member.name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f: f.write(data)
print('ALL_70_MEMBERS_VERIFIED')
PY
```

The original failed run is Verify 42186062706, composition-tiny job 127787874362,
merge `5728a4f1b43d9d66f6cea8467ac3443efe14297e`. Its complete decoded log text
is UTF-8 encoded (original BOM/ANSI/newlines retained) in the separate `.log.b64`.
The prior failure remains failure. This package includes no new ARM, physical
DUT, real KWS or subjective intercom measurement.
