#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--name',required=True); p.add_argument('--version',required=True); p.add_argument('--revision',required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--created-epoch',type=int,required=True); a=p.parse_args()
    files=[]
    for path in sorted(x for x in a.root.rglob('*') if x.is_file()):
        rel=path.relative_to(a.root).as_posix(); sid='SPDXRef-File-'+hashlib.sha256(rel.encode()).hexdigest()[:16]
        files.append({'SPDXID':sid,'fileName':'./'+rel,'checksums':[{'algorithm':'SHA256','checksumValue':sha256(path)}]})
    created=datetime.fromtimestamp(a.created_epoch,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    doc={'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0','SPDXID':'SPDXRef-DOCUMENT','name':f'{a.name}-{a.version}','documentNamespace':f'https://github.com/jiying2007/audio-pipeline/releases/tag/v{a.version}#{a.revision}','creationInfo':{'created':created,'creators':['Tool: audio-pipeline/generate_spdx_sbom.py']},'packages':[{'name':a.name,'SPDXID':'SPDXRef-Package','versionInfo':a.version,'downloadLocation':'NOASSERTION','filesAnalyzed':True,'packageVerificationCode':{'packageVerificationCodeValue':hashlib.sha1("".join(x['checksums'][0]['checksumValue'] for x in files).encode()).hexdigest()}}],'files':files,'relationships':[{'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES','relatedSpdxElement':'SPDXRef-Package'}]+[{'spdxElementId':'SPDXRef-Package','relationshipType':'CONTAINS','relatedSpdxElement':f['SPDXID']} for f in files]}
    a.output.write_text(json.dumps(doc,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
if __name__=='__main__': main()
