"""Build desktop Ruffle with the same pinned core fixes as the browser runtime."""
import argparse
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def build(work, output):
    lock = json.loads((ROOT / 'ruffle/lock.json').read_text())
    version = subprocess.check_output(['rustc', '--version'], text=True)
    if not version.startswith('rustc ' + lock['rustVersion'] + ' '):
        raise RuntimeError('Desktop build requires Rust ' + lock['rustVersion'])
    work.mkdir(parents=True)
    with urlopen(f'https://codeload.github.com/ruffle-rs/ruffle/tar.gz/{lock["sourceCommit"]}', timeout=120) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != lock['sourceSha256']:
        raise RuntimeError('Desktop Ruffle source checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(work, filter='data')
    source = work / ('ruffle-' + lock['sourceCommit'])
    patches = {}
    for name in lock['patches']:
        patch = ROOT / 'ruffle/patches' / name
        patches[name] = hashlib.sha256(patch.read_bytes()).hexdigest()
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True)
    desktop_patch = ROOT / 'desktop/patches/0001-inline-graphic-inspector.patch'
    subprocess.run(['git', 'apply', '--check', str(desktop_patch)], cwd=source, check=True)
    subprocess.run(['git', 'apply', str(desktop_patch)], cwd=source, check=True)
    env = {**os.environ, 'CARGO_PROFILE_RELEASE_LTO': 'false', 'CARGO_PROFILE_RELEASE_CODEGEN_UNITS': '16',
           'CARGO_PROFILE_RELEASE_OPT_LEVEL': '2', 'CARGO_PROFILE_RELEASE_DEBUG': '0', 'CARGO_PROFILE_RELEASE_INCREMENTAL': 'false'}
    subprocess.run(['cargo', 'build', '--locked', '--release', '-p', 'ruffle_desktop'], cwd=source, env=env, check=True)
    target = Path(env['CARGO_TARGET_DIR']) if 'CARGO_TARGET_DIR' in env else source / 'target'
    provenance = {'version': lock['version'], 'sourceCommit': lock['sourceCommit'], 'patches': patches,
                  'rustVersion': lock['rustVersion'], 'desktopPatches': {desktop_patch.name: hashlib.sha256(desktop_patch.read_bytes()).hexdigest()},
                  'client': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    files = {'ruffle': (target / 'release/ruffle').read_bytes(), 'LICENSE.md': (source / 'LICENSE.md').read_bytes(),
             'README.md': (source / 'README.md').read_bytes(), 'openrotmg.json': (json.dumps(provenance, indent=2) + '\n').encode()}
    with output.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as compressed, tarfile.open(fileobj=compressed, mode='w') as bundle:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o755 if name == 'ruffle' else 0o644
            bundle.addfile(entry, io.BytesIO(data))
    print(hashlib.sha256(output.read_bytes()).hexdigest(), output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.work_dir.resolve(), args.output.resolve())
