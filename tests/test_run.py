import hashlib
import io
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run


class LauncherTests(unittest.TestCase):
    def test_asset_root_is_the_client_repository(self):
        self.assertEqual(run.ROOT, Path(__file__).resolve().parents[1])

    def test_shell_entrypoint_works_from_another_directory(self):
        with tempfile.TemporaryDirectory(prefix="launcher with spaces ") as directory:
            result = subprocess.run([str(run.ROOT / "run.sh"), "--help"], cwd=directory,
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prepare-only", result.stdout)
        self.assertIn("--dev-control", result.stdout)

    def test_conflicting_modes_fail_before_preparing_assets(self):
        result = subprocess.run([str(run.ROOT / "run.sh"), "--prepare-only", "--dev-control"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not allowed", result.stderr)
        self.assertNotIn("Prepared Ruffle", result.stdout)


class ClientRoutingTests(unittest.TestCase):
    def test_loading_status_clears_without_gameplay_disclaimers(self):
        html = (run.ROOT / "launcher.js").read_text()
        self.assertIn("document.querySelector('#status').textContent = '';", html)
        self.assertIn("document.querySelector('#status').textContent = String(error);", html)
        self.assertNotIn("historically verified game", html)
        self.assertNotIn("historical fidelity", html)
        self.assertNotIn("External requests are blocked", html)

    def test_focus_loss_releases_held_game_keys(self):
        result = subprocess.run(["node", "--test", str(run.ROOT / "tests/input.mjs"), str(run.ROOT / "tests/launcher.mjs")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_only_legacy_game_account_picture_api_urls_are_rewritten(self):
        html = (run.ROOT / "launcher.js").read_text()
        pattern = re.search(r"\[/([^\n]+?)/,accountEndpoint\]", html).group(1).replace(r"\/", "/")
        for port in [8080, 18923, 65535]:
            origin = f"http://127.0.0.1:{port}"
            for path in ["client.swf", "vendor/ruffle.js", "sfx/death_screen.mp3", "legacy-api/char/list", "game", "health"]:
                with self.subTest(port=port, path=path):
                    url = f"{origin}/{path}"
                    self.assertEqual(re.sub(pattern, origin + "/legacy-api/", url), url)
            for protocol in ["http", "https"]:
                for path in ["char/list", "char/fame", "account/register", "account/verify", "fame/list", "guild/listMembers", "guild/getBoard", "guild/setBoard",
                             "picture/save", "picture/list", "picture/get", "picture/delete"]:
                    url = f"{protocol}://127.0.0.1:8080/{path}"
                    self.assertEqual(re.sub(pattern, origin + "/legacy-api/", url), origin + "/legacy-api/" + path)
        for foreign in ["https://127.0.0.1.evil.example:8080/char/list", "http://127.0.0.1:8080/accounting/report", "http://127.0.0.1:8080/credits/buy",
                        "http://127.0.0.1:8080/pictures/list", "http://127.0.0.1:8080/picture",
                        "http://127.0.0.1:8081/picture/get", "http://localhost:8080/picture/get",
                        "http://127.0.0.1:8080.evil.example/picture/get", "http://127.0.0.1:8080@evil.example/picture/get",
                        "http://evil.example/picture/get", "ftp://127.0.0.1:8080/picture/get",
                        "http://127.0.0.1:8080/not/picture/get", "http://127.0.0.1:8080/?next=/picture/get"]:
            self.assertEqual(re.sub(pattern, "/legacy-api/", foreign), foreign)


class RufflePreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        patches = self.root / 'ruffle/patches'
        patches.mkdir(parents=True)
        for name in run.LOCK['patches']:
            shutil.copyfile(run.ROOT / 'ruffle/patches' / name, patches / name)
        metadata = {
            'version': run.VERSION, 'sourceCommit': run.LOCK['sourceCommit'],
            'patches': {n: hashlib.sha256((patches / n).read_bytes()).hexdigest()
                        for n in run.LOCK['patches']}
        }
        self.files = {'ruffle.js': b'loader', 'core.ruffle.a.js': b'simd',
                      'core.ruffle.b.js': b'mvp', 'a.wasm': b'simd wasm',
                      'b.wasm': b'mvp wasm', 'LICENSE_MIT': b'mit',
                      'LICENSE_APACHE': b'apache',
                      'openrotmg.json': json.dumps(metadata).encode()}

    def bundle(self, files):
        output = io.BytesIO()
        with ZipFile(output, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return output.getvalue()

    def prepare(self, data):
        cache = self.root / f'.ruffle-{run.VERSION}.zip'
        cache.write_bytes(data)
        with patch.object(run, 'ROOT', self.root), patch.object(
                run, 'SHA256', hashlib.sha256(data).hexdigest()), redirect_stdout(io.StringIO()):
            run.prepare_ruffle()
        return cache

    def test_preparation_is_repeatable_and_replaces_stale_assets(self):
        data = self.bundle(self.files)
        cache = self.prepare(data)
        (self.root / 'vendor/stale.wasm').write_bytes(b'old runtime')
        self.prepare(data)
        self.assertEqual(cache.read_bytes(), data)
        self.assertEqual(set(p.name for p in (self.root / 'vendor').iterdir()), set(self.files))
        for name, expected in self.files.items():
            self.assertEqual((self.root / 'vendor' / name).read_bytes(), expected)

    def test_corrupt_archive_rejected_before_touching_vendor(self):
        self.prepare(self.bundle(self.files))
        (self.root / f'.ruffle-{run.VERSION}.zip').write_bytes(b'corrupt')
        with patch.object(run, 'ROOT', self.root), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'Ruffle checksum mismatch'):
                run.prepare_ruffle()
        self.assertEqual((self.root / 'vendor/ruffle.js').read_bytes(), b'loader')

    def test_missing_variant_or_path_escape_rejected(self):
        for missing in ['a.wasm', 'LICENSE_MIT']:
            files = dict(self.files)
            files['../outside.js'] = files.pop(missing)
            with self.subTest(missing=missing), self.assertRaisesRegex(RuntimeError, 'bundle contents'):
                self.prepare(self.bundle(files))
        self.assertFalse((self.root.parent / 'outside.js').exists())

    def test_wrong_source_version_or_patch_provenance_rejected(self):
        for key in ['version', 'sourceCommit', 'patches']:
            files = dict(self.files)
            metadata = json.loads(files['openrotmg.json'])
            metadata[key] = {} if key == 'patches' else 'wrong'
            files['openrotmg.json'] = json.dumps(metadata).encode()
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'provenance mismatch'):
                self.prepare(self.bundle(files))
        self.assertFalse((self.root / 'vendor').exists())

    def test_changed_source_patch_invalidates_bundle(self):
        name = run.LOCK['patches'][0]
        (self.root / 'ruffle/patches' / name).write_text('different source fix')
        with self.assertRaisesRegex(RuntimeError, 'provenance mismatch'):
            self.prepare(self.bundle(self.files))

    def test_download_is_verified_and_cached(self):
        data = self.bundle(self.files)
        with patch.object(run, 'ROOT', self.root), patch.object(
                run, 'SHA256', hashlib.sha256(data).hexdigest()), patch.object(
                run, 'urlopen', return_value=io.BytesIO(data)) as fetch, redirect_stdout(io.StringIO()):
            run.prepare_ruffle()
        fetch.assert_called_once_with(run.URL, timeout=120)
        self.assertEqual((self.root / f'.ruffle-{run.VERSION}.zip').read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
