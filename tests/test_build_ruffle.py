import io
import json
import os
import tarfile
import re
import subprocess
import tempfile
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_ruffle


class CompilerPathTests(unittest.TestCase):
    def test_normalized_arguments_across_homes_and_custom_roots_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='compiler paths ') as directory:
            for home_name, custom in [('local home', False), ('runner home', False), ('custom home', True)]:
                home = Path(directory) / home_name
                source = home / 'checkout with spaces'
                cargo = home / ('custom cargo' if custom else '.cargo')
                sysroot = home / 'custom rustup/toolchains/pinned'
                rust_src = sysroot / 'lib/rustlib/src/rust'
                rust_src.mkdir(parents=True)
                source.mkdir(parents=True)
                env = {'HOME': str(home), 'RUSTC': '/compiler with spaces/rustc'}
                if custom:
                    env['CARGO_HOME'] = str(cargo)
                with patch.object(subprocess, 'check_output', return_value=str(sysroot)) as compiler:
                    encoded = build_ruffle.wasm_rustflags(source, '-C target-cpu=mvp', env)
                compiler.assert_called_once_with([env['RUSTC'], '--print', 'sysroot'], cwd=source, env=env, text=True)
                self.assertEqual(encoded.split('\x1f'), [
                    '--cfg=web_sys_unstable_apis', '--cfg=getrandom_backend="wasm_js"', '-Aunknown_lints',
                    '-C', 'target-cpu=mvp',
                    f'--remap-path-prefix={cargo}=/cargo',
                    f'--remap-path-prefix={source}=/ruffle',
                    f'--remap-path-prefix={rust_src}=/rust-src'])

    def test_relative_cargo_symlink_remaps_both_spellings(self):
        with tempfile.TemporaryDirectory(prefix='linked paths ') as directory:
            source = Path(directory)
            cargo = source / 'actual cargo'
            cargo.mkdir()
            (source / 'cargo link').symlink_to(cargo, target_is_directory=True)
            (source / 'lib/rustlib/src/rust').mkdir(parents=True)
            with patch.object(subprocess, 'check_output', return_value=directory):
                args = build_ruffle.wasm_rustflags(source, '-C target-cpu=mvp', {'CARGO_HOME': 'cargo link'}).split('\x1f')
            self.assertIn(f'--remap-path-prefix={source / "cargo link"}=/cargo', args)
            self.assertIn(f'--remap-path-prefix={cargo}=/cargo', args)
            self.assertLess(args.index(f'--remap-path-prefix={source}=/ruffle'), args.index(f'--remap-path-prefix={cargo}=/cargo'))

    def test_conflicting_roots_fail_instead_of_losing_a_mapping(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(subprocess, 'check_output', return_value=directory):
            source = Path(directory)
            (source / 'lib/rustlib/src/rust').mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, 'Conflicting compiler path roots'):
                build_ruffle.wasm_rustflags(source, '-C target-cpu=mvp', {'CARGO_HOME': directory})

    def test_encoded_separator_in_path_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(subprocess, 'check_output', return_value=directory):
            source = Path(directory)
            (source / 'lib/rustlib/src/rust').mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, 'encoded-flags separator'):
                build_ruffle.wasm_rustflags(source, '-C target-cpu=mvp', {'CARGO_HOME': '/bad\x1fpath'})

    def test_missing_rust_sources_fail_clearly(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(subprocess, 'check_output', return_value=directory):
            with self.assertRaisesRegex(RuntimeError, 'Missing rust-src'):
                build_ruffle.wasm_rustflags(Path(directory), '-C target-cpu=mvp', {'HOME': directory})

    def test_both_actual_cargo_environments_override_inherited_encoded_flags(self):
        with tempfile.TemporaryDirectory(prefix='build boundary ') as directory:
            root = Path(directory)
            lock = json.loads((build_ruffle.ROOT / 'ruffle/lock.json').read_text()) | {'patches': []}
            (root / 'ruffle/patches').mkdir(parents=True)
            (root / 'ruffle/tests').mkdir()
            (root / 'ruffle/lock.json').write_text(json.dumps(lock))
            work = root / 'new build'
            source = work / ('ruffle-' + lock['sourceCommit'])
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode='w:gz') as archive:
                for name in ['ruffle.js', 'core.a.js', 'core.b.js', 'a.wasm', 'b.wasm', 'LICENSE_MIT', 'LICENSE_APACHE']:
                    entry = tarfile.TarInfo('ruffle-' + lock['sourceCommit'] + '/web/packages/selfhosted/dist/' + name)
                    entry.size = 1
                    archive.addfile(entry, io.BytesIO(b'x'))
            lock['sourceSha256'] = build_ruffle.hashlib.sha256(data.getvalue()).hexdigest()
            (root / 'ruffle/lock.json').write_text(json.dumps(lock))
            rust_src = root / 'rustup/lib/rustlib/src/rust'
            rust_src.mkdir(parents=True)
            def tool(command, **kwargs):
                return {'rustc': 'rustc ' + lock['rustVersion'] + ' (pinned)', 'wasm-bindgen': 'wasm-bindgen ' + lock['wasmBindgenVersion'], 'node': 'v22.23.2'}[command[0]] if command[-1] == '--version' else str(root / 'rustup')
            with patch.object(build_ruffle, 'ROOT', root), patch.object(build_ruffle, 'urlopen', return_value=io.BytesIO(data.getvalue())), patch.object(
                    subprocess, 'check_output', side_effect=tool), patch.object(subprocess, 'run') as run, patch.dict(
                    os.environ, {'HOME': str(root), 'CARGO_HOME': str(root / 'cargo home'),
                                 'RUSTFLAGS': '--invalid-outer-flag', 'CARGO_ENCODED_RUSTFLAGS': '--invalid-encoded-flag'}, clear=True):
                build_ruffle.build(work, root / 'output.zip')
            builds = [call for call in run.call_args_list if call.args[0][:2] == ['cargo', 'build']]
            self.assertEqual(len(builds), 2)
            for call, flavor, target in zip(builds, ['extensions', 'mvp'], [
                    'target-feature=+bulk-memory,+simd128,+nontrapping-fptoint,+sign-ext,+reference-types', 'target-cpu=mvp']):
                env = call.kwargs['env']
                effective = env['CARGO_ENCODED_RUSTFLAGS'].split('\x1f')
                self.assertEqual(effective[:5], ['--cfg=web_sys_unstable_apis', '--cfg=getrandom_backend="wasm_js"', '-Aunknown_lints', '-C', target])
                self.assertEqual(effective[5:], [f'--remap-path-prefix={root / "cargo home"}=/cargo', f'--remap-path-prefix={rust_src}=/rust-src', f'--remap-path-prefix={source}=/ruffle'])
                self.assertEqual(env['RUSTC_BOOTSTRAP'], '1' if flavor == 'mvp' else '0')
                self.assertEqual(env['CFLAGS_wasm32_unknown_unknown'], '-mno-reference-types -mno-multivalue')
                self.assertEqual(call.args[0], ['cargo', 'build', '--locked', '-p', 'ruffle_web', '--target', 'wasm32-unknown-unknown', '--profile', 'web-wasm-' + flavor] + (['-Z', 'build-std=std,panic_abort'] if flavor == 'mvp' else []))


class BuildPinTests(unittest.TestCase):
    def test_pixelbender_rust_and_swf_fixtures_use_identical_bytecode(self):
        fixture = build_ruffle.ROOT / 'ruffle/tests/openrotmg_pixelbender_program_cache'
        hex_program = re.search(r'var hex:String = "([0-9a-f]+)"', (fixture / 'Test.as').read_text())[1]
        self.assertEqual(bytes.fromhex(hex_program), (fixture / 'shader.pbj').read_bytes())

    def test_wrong_compiler_fails_before_download_or_build(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                subprocess, 'check_output', return_value='rustc 0.0.0'), patch.object(
                build_ruffle, 'urlopen') as fetch:
            work = Path(directory) / 'new'
            with self.assertRaisesRegex(RuntimeError, 'Build tool mismatch'):
                build_ruffle.build(work, Path(directory) / 'bundle.zip')
            fetch.assert_not_called()
            self.assertFalse(work.exists())

    def test_source_checksum_fails_before_extracting_or_patching(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                subprocess, 'check_output', side_effect=[
                    'rustc 1.99.0 (pinned)', 'wasm-bindgen 0.2.127', 'v22.22.3']), patch.object(
                build_ruffle, 'urlopen', return_value=io.BytesIO(b'wrong source')), patch.object(
                subprocess, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'source archive checksum mismatch'):
                build_ruffle.build(Path(directory) / 'new', Path(directory) / 'bundle.zip')
            command.assert_not_called()
            self.assertFalse((Path(directory) / 'bundle.zip').exists())
