import copy
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_editor as editor


class NativeEditorPreparationTests(unittest.TestCase):
    def setUp(self):
        self.source = (editor.ROOT / 'client.swf').read_bytes()

    def test_exact_entry_only_artifact_and_unchanged_gameplay(self):
        result = editor.derive_editor(self.source)
        self.assertEqual(hashlib.sha256(result).hexdigest(), 'b102f0a779e4013f945b4576a716d7b7fc2dd60f84bfd8a89361e0ffc9f7023b')
        self.assertEqual(len(result), struct.unpack_from('<I', result, 4)[0])
        self.assertEqual(len(editor.LOCK['edits']), 6)
        restored = result
        for edit in reversed(editor.LOCK['edits']):
            offset = edit['offset']
            before, after = bytes.fromhex(edit['before']), bytes.fromhex(edit['after'])
            self.assertEqual(restored[offset:offset + len(after)], after)
            restored = restored[:offset] + before + restored[offset + len(after):]
        self.assertEqual(restored, self.source)
        self.assertEqual((editor.ROOT / 'client.swf').read_bytes(), self.source)

    def test_unknown_or_corrupt_source_rejected(self):
        for data in [b'', self.source[:-1], b'CWS' + self.source[3:]]:
            with self.assertRaisesRegex(RuntimeError, 'source checksum mismatch'):
                editor.derive_editor(data)

    def test_each_target_and_output_checksum_are_checked(self):
        for index in range(6):
            lock = copy.deepcopy(editor.LOCK)
            lock['edits'][index]['before'] = '00'
            with patch.object(editor, 'LOCK', lock), self.assertRaisesRegex(RuntimeError, 'target mismatch'):
                editor.derive_editor(self.source)
        lock = copy.deepcopy(editor.LOCK)
        lock['outputSha256'] = '0' * 64
        with patch.object(editor, 'LOCK', lock), self.assertRaisesRegex(RuntimeError, 'derived checksum mismatch'):
            editor.derive_editor(self.source)

    def test_repeatable_preparation_and_corrupt_artifact_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(editor, 'ROOT', Path(directory)):
            source = editor.ROOT / 'client.swf'
            source.write_bytes(self.source)
            editor.prepare_editor()
            target = editor.ROOT / editor.LOCK['artifact']
            first = target.stat().st_mtime_ns
            editor.prepare_editor()
            self.assertEqual(target.stat().st_mtime_ns, first)
            target.write_bytes(b'corrupt artifact evidence')
            with self.assertRaisesRegex(RuntimeError, 'artifact checksum mismatch'):
                editor.prepare_editor()
            self.assertEqual(target.read_bytes(), b'corrupt artifact evidence')
            source.write_bytes(b'wrong source')
            with self.assertRaisesRegex(RuntimeError, 'source checksum mismatch'):
                editor.prepare_editor()
            self.assertEqual(target.read_bytes(), b'corrupt artifact evidence')


if __name__ == '__main__':
    unittest.main()
