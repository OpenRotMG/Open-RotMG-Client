#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile
from prepare_editor import prepare_editor

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'ruffle/lock.json').read_text())
VERSION = LOCK['version']
URL = f'https://github.com/OpenRotMG/Open-RotMG-Client/releases/download/ruffle-{VERSION}/ruffle-{VERSION}.zip'
SHA256 = LOCK['bundleSha256']


def prepare_ruffle():
    cache = ROOT / f'.ruffle-{VERSION}.zip'
    if cache.exists():
        print(f'Using cached Ruffle {VERSION}', flush=True)
        data = cache.read_bytes()
    else:
        print(f'Downloading Ruffle {VERSION}: {URL}', flush=True)
        with urlopen(URL, timeout=120) as response:
            data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != SHA256:
        raise RuntimeError(f'Ruffle checksum mismatch: expected {SHA256}, got {actual}. Remove {cache} and rerun.')
    with ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        required = {'ruffle.js', 'LICENSE_MIT', 'LICENSE_APACHE', 'openrotmg.json'}
        if (len(names) != 8 or len(set(names)) != 8 or not required.issubset(names)
                or any('/' in n or '\\' in n for n in names)
                or sum(n.endswith('.wasm') for n in names) != 2
                or sum(n.endswith('.js') for n in names) != 3):
            raise RuntimeError(f'Unexpected dual Ruffle bundle contents: {names}')
        provenance = json.loads(archive.read('openrotmg.json'))
        patches = {name: hashlib.sha256((ROOT / 'ruffle/patches' / name).read_bytes()).hexdigest()
                   for name in LOCK['patches']}
        if (provenance['version'] != VERSION or provenance['sourceCommit'] != LOCK['sourceCommit']
                or provenance['patches'] != patches):
            raise RuntimeError('Ruffle bundle source/patch provenance mismatch')
        with tempfile.TemporaryDirectory(prefix='.ruffle-stage-', dir=ROOT) as temporary:
            staged = Path(temporary) / 'vendor'
            archive.extractall(staged)
            if (ROOT / 'vendor').exists():
                shutil.rmtree(ROOT / 'vendor')
            staged.rename(ROOT / 'vendor')
    if not cache.exists():
        cache.write_bytes(data)
    print(f'Prepared Ruffle {VERSION}: verified dual runtime and {len(patches)} source patches', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare Ruffle and start the OpenRotMG development backend.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-only', action='store_true', help='Install Ruffle without starting the backend')
    mode.add_argument('--dev-control', action='store_true', help="Enable the backend's loopback script control")
    args = parser.parse_args()
    server = ROOT.parent / 'server'
    if not args.prepare_only:
        if not (server / 'Cargo.toml').is_file():
            parser.error(f'Missing sibling Rust server: {server / "Cargo.toml"}. Clone https://github.com/OpenRotMG/Open-RotMG-Server into a sibling server directory.')
        if shutil.which('cargo') is None:
            parser.error('Cargo not found. Install Rust/Cargo from https://rustup.rs/ and rerun.')
    prepare_editor()
    prepare_ruffle()
    if not args.prepare_only:
        command = ['cargo', 'run', '--locked'] + (['--', '--dev-control'] if args.dev_control else [])
        print(f'Starting backend in {server}\nClient: http://127.0.0.1:18923/', flush=True)
        try:
            raise SystemExit(subprocess.call(command, cwd=server))
        except KeyboardInterrupt:
            raise SystemExit(130)
