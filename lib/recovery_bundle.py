"""Deterministic, secret-free single-file Live USB recovery exporter."""
import base64
import hashlib
import io
import os
from pathlib import Path
import tempfile
import zipfile
from recovery_platform import safe_path
from recovery import VERSION

MODULES=('recovery_catalog','recovery_platform','recovery_transaction','recovery')


def payload():
    output=io.BytesIO()
    sources={name+'.py':(Path(__file__).parent/(name+'.py')).read_bytes() for name in MODULES}
    sources['__main__.py']=b'import sys\nfrom recovery import entrypoint\nsys.exit(entrypoint())\n'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(sources.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o644<<16
            archive.writestr(info,data)
    return output.getvalue()


def launcher(data):
    encoded=base64.b64encode(data).decode(); digest=hashlib.sha256(data).hexdigest()
    return ('''#!/usr/bin/env bash
# Autonomous ws-restore; no workstation config, credentials or local state included.
set -euo pipefail
command -v python3 >/dev/null 2>&1 || { echo 'ws-restore: python3 is required on Live USB' >&2; exit 69; }
umask 077
payload_dir="$(mktemp -d -t ws-restore-payload-XXXXXXXX)"
cleanup() { rm -f -- "$payload_dir/recovery.pyz"; rmdir -- "$payload_dir"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
WS_PAYLOAD='''+"'"+encoded+"'"+'''
python3 - "$payload_dir/recovery.pyz" "$WS_PAYLOAD" '''+digest+''' <<'WS_DECODE'
import base64,hashlib,sys
try:
 data=base64.b64decode(sys.argv[2],validate=True)
 if hashlib.sha256(data).hexdigest()!=sys.argv[3]: raise ValueError('SHA-256 mismatch')
 with open(sys.argv[1],'xb') as output: output.write(data)
except (ValueError,OSError) as error:
 print('ws-restore: invalid embedded payload: '+str(error),file=sys.stderr)
 sys.exit(1)
WS_DECODE
unset WS_PAYLOAD
python3 "$payload_dir/recovery.pyz" "$@"
''').encode()


def export_bundle(output,overwrite=False):
    output=safe_path(Path(output).absolute())
    if output.exists() and not overwrite: raise FileExistsError('export output already exists')
    data=launcher(payload())
    fd,name=tempfile.mkstemp(prefix='.ws-restore-',dir=output.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush(); os.fchmod(stream.fileno(),0o755); os.fsync(stream.fileno())
        if overwrite: os.replace(name,output)
        else: os.link(name,output)
        directory=os.open(output.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)
    return {'output':str(output),'sha256':hashlib.sha256(data).hexdigest(),'version':VERSION}
