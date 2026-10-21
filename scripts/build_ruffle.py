#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.request import urlopen
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def build(work, output):
    lock = json.loads((ROOT / 'ruffle/lock.json').read_text())
    for command, expected in [([os.environ.get('RUSTC', 'rustc'), '--version'], 'rustc ' + lock['rustVersion'] + ' '),
                              (['wasm-bindgen', '--version'], 'wasm-bindgen ' + lock['wasmBindgenVersion'])]:
        actual = subprocess.check_output(command, text=True).strip()
        if not actual.startswith(expected):
            raise RuntimeError(f'Build tool mismatch: expected {expected}, got {actual}')
    if subprocess.check_output(['node', '--version'], text=True).split('.')[0] != 'v22':
        raise RuntimeError('The pinned Ruffle build requires Node22')
    work.mkdir(parents=True)
    url = f"https://codeload.github.com/ruffle-rs/ruffle/tar.gz/{lock['sourceCommit']}"
    print(f"Source {lock['sourceCommit']}: {url}", flush=True)
    with urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != lock['sourceSha256']:
        raise RuntimeError('Ruffle source archive checksum mismatch')
    archive = work / 'source.tar.gz'
    archive.write_bytes(data)
    with tarfile.open(archive) as source:
        source.extractall(work, filter='data')
    source = work / ('ruffle-' + lock['sourceCommit'])
    patches = {}
    if set(lock['patches']) != {p.name for p in (ROOT / 'ruffle/patches').glob('*.patch')}:
        raise RuntimeError('Ruffle patch set differs from the lock')
    for name in lock['patches']:
        patch = ROOT / 'ruffle/patches' / name
        patches[patch.name] = hashlib.sha256(patch.read_bytes()).hexdigest()
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True)
    shutil.copytree(ROOT / 'ruffle/tests', source / 'tests/tests/swfs/avm2', dirs_exist_ok=True)
    web = source / 'web'
    env = os.environ | {'BUILD_WASM_MVP': 'true', 'ENABLE_VERSION_SEAL': 'true'}
    def run(command, cwd=source, extra=None):
        print('+ ' + ' '.join(command), flush=True)
        subprocess.run(command, cwd=cwd, env=env | (extra or {}), check=True)
    run(['npm', 'ci', '--no-audit', '--no-fund'], web)
    run(['npm', 'run', 'test', '--workspace=ruffle-core', '--', '--grep', 'Advancement'], web)
    run(['cargo', 'test', '--locked', '-p', 'ruffle_core'])
    run(['cargo', 'test', '--locked', '-p', 'ruffle_render', '--features', 'tessellator'])
    run(['cargo', 'test', '--locked', '-p', 'ruffle_render_wgpu'])
    for test in ['textline_', 'bitmapdata_draw', 'bitmapdata_clone', 'openrotmg_bitmap_compat', 'openrotmg_focus_activation', 'mouse_wheel_events', 'openrotmg_wheel_accumulator',
                 'openrotmg_unused_locals', 'openrotmg_slot_read', 'openrotmg_sort_snapshot', 'openrotmg_bitmap_batch', 'openrotmg_pixelbender_program_cache']:
        run(['cargo', 'test', '--locked', '-p', 'tests', '--features', 'imgtests', '--test', 'tests', test, '--', '--test-threads', '4'])
    dist = web / 'packages/core/dist'
    dist.mkdir(parents=True, exist_ok=True)
    for flavor, name, flags in [
        ('extensions', 'ruffle_web', '-C target-feature=+bulk-memory,+simd128,+nontrapping-fptoint,+sign-ext,+reference-types'),
        ('mvp', 'ruffle_web-wasm_mvp', '-C target-cpu=mvp')
    ]:
        rustflags = '--cfg=web_sys_unstable_apis --cfg=getrandom_backend="wasm_js" -Aunknown_lints ' + flags
        command = ['cargo', 'build', '--locked', '-p', 'ruffle_web', '--target', 'wasm32-unknown-unknown', '--profile', 'web-wasm-' + flavor]
        if flavor == 'mvp':
            command += ['-Z', 'build-std=std,panic_abort']
        run(command, extra={'RUSTFLAGS': rustflags, 'RUSTC_BOOTSTRAP': '1' if flavor == 'mvp' else '0',
                            'CFLAGS_wasm32_unknown_unknown': '-mno-reference-types -mno-multivalue'})
        wasm = Path(env['CARGO_TARGET_DIR']) if 'CARGO_TARGET_DIR' in env else source / 'target'
        command = ['wasm-bindgen', str(wasm / 'wasm32-unknown-unknown' / ('web-wasm-' + flavor) / 'ruffle_web.wasm'),
                   '--target', 'web', '--out-dir', str(dist), '--out-name', name]
        if flavor == 'extensions':
            command.append('--reference-types')
        run(command)
    seal = {'version_number': lock['version'], 'version_name': lock['version'], 'version_channel': 'stable',
            'build_date': lock['buildDate'], 'commitHash': lock['sourceCommit'], 'version4': '', 'firefox_extension_id': 'ruffle@ruffle.rs'}
    (web / 'version_seal.json').write_text(json.dumps(seal))
    run(['npm', 'exec', '--workspace=ruffle-core', '--', 'tsc', '--build', '--force'], web)
    run(['npm', 'run', 'postbuild', '--workspace=ruffle-core'], web)
    run(['npm', 'run', 'build', '--workspace=ruffle-selfhosted'], web)
    files = {p.name: p.read_bytes() for p in (web / 'packages/selfhosted/dist').iterdir()
             if p.suffix in ['.js', '.wasm'] or p.name in ['LICENSE_MIT', 'LICENSE_APACHE']}
    if len(files) != 7 or len([n for n in files if n.endswith('.wasm')]) != 2 or 'ruffle.js' not in files:
        raise RuntimeError(f'Unexpected dual-runtime output: {sorted(files)}')
    files['openrotmg.json'] = (json.dumps({'version': lock['version'], 'sourceCommit': lock['sourceCommit'],
        'patches': patches, 'rustVersion': lock['rustVersion'], 'wasmBindgenVersion': lock['wasmBindgenVersion']}, indent=2) + '\n').encode()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = ZipInfo(name, (2026, 10, 14, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED)
    print(f"Bundle SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()} {output}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build both pinned Ruffle WASM variants with the client source patches. Requires Rust with rust-src/wasm32, wasm-bindgen and Node22.')
    parser.add_argument('--work-dir', required=True, type=Path, help='New build directory; retained for debugging')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    build(args.work_dir.resolve(), args.output.resolve())
