import io
import re
import subprocess
import tempfile
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_ruffle


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
