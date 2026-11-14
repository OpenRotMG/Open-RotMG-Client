import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('build_desktop', Path(__file__).parents[1] / 'scripts/build_desktop.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopBuildTest(unittest.TestCase):
    def test_sealed_source_and_patches_produce_an_executable_with_exact_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / 'client'
            (client / 'ruffle/patches').mkdir(parents=True)
            (client / 'desktop/patches').mkdir(parents=True)
            (client / 'ruffle/patches/core.patch').write_bytes(b'core fix')
            (client / 'desktop/patches/0001-inline-graphic-inspector.patch').write_bytes(b'inspector fix')
            source = io.BytesIO()
            with tarfile.open(fileobj=source, mode='w:gz') as archive:
                for name in ['LICENSE.md', 'README.md']:
                    entry = tarfile.TarInfo('ruffle-' + 'a' * 40 + '/' + name)
                    value = name.encode()
                    entry.size = len(value)
                    archive.addfile(entry, io.BytesIO(value))
            data = source.getvalue()
            lock = {'version': '0.7.1-openrotmg.16', 'rustVersion': '1.99.0', 'sourceCommit': 'a' * 40,
                    'sourceSha256': hashlib.sha256(data).hexdigest(), 'patches': ['core.patch']}
            (client / 'ruffle/lock.json').write_text(json.dumps(lock))

            def run(command, cwd, **kwargs):
                if command[0] == 'cargo':
                    target = cwd / 'target/release'
                    target.mkdir(parents=True)
                    (target / 'ruffle_desktop').write_bytes(b'executable')

            def output(command, **kwargs):
                return 'rustc 1.99.0 (fixture)' if command[0] == 'rustc' else 'b' * 40 + '\n'

            with patch.object(desktop, 'ROOT', client), patch.object(desktop, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(data)), \
                    patch.object(desktop.subprocess, 'run', side_effect=run) as commands, \
                    patch.object(desktop.subprocess, 'check_output', side_effect=output), patch.dict(desktop.os.environ, {}, clear=True):
                bundle = root / 'desktop.tar.gz'
                desktop.build(root / 'build', bundle)
                with tarfile.open(bundle) as archive:
                    self.assertEqual(archive.extractfile('ruffle').read(), b'executable')
                    self.assertEqual(archive.getmember('ruffle').mode, 0o755)
                    provenance = json.load(archive.extractfile('openrotmg.json'))
                    self.assertEqual(provenance['client'], 'b' * 40)
                    self.assertEqual(provenance['patches'], {'core.patch': hashlib.sha256(b'core fix').hexdigest()})
                    self.assertEqual(provenance['desktopPatches']['0001-inline-graphic-inspector.patch'], hashlib.sha256(b'inspector fix').hexdigest())
                self.assertEqual(len(commands.call_args_list), 5)
                with patch.object(desktop.subprocess, 'check_output', return_value='rustc 1.98.0'):
                    with self.assertRaisesRegex(RuntimeError, 'requires Rust'):
                        desktop.build(root / 'wrong-compiler', bundle)
                with patch.object(desktop, 'urlopen', return_value=io.BytesIO(b'wrong source')):
                    with self.assertRaisesRegex(RuntimeError, 'source checksum'):
                        desktop.build(root / 'wrong-source', bundle)
