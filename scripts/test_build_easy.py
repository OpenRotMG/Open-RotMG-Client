import os
from pathlib import Path
import struct
import tempfile
import unittest

import build_easy as easy

ROOT = Path(__file__).resolve().parents[1]


class EasyClientTest(unittest.TestCase):
    def test_missing_anchor_fails_instead_of_shipping_a_partial_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Parameters.class.asasm'
            path.write_text('  trait method QName(PackageNamespace(""), "load")\n   code\n  end ; trait\n')
            with self.assertRaisesRegex(RuntimeError, 'Easy Client anchor'):
                easy.edit(path, 'trait method QName(PackageNamespace(""), "load")', '"AssembleeGameClientOptions"', '"x"')

    @unittest.skipUnless(os.environ.get('RABCDASM'), 'Set RABCDASM for native assembly tests')
    def test_reference_movie_gains_easy_options_platform_and_teleport_input(self):
        movie = easy.build(Path(os.environ['RABCDASM']).resolve(), (ROOT / 'web/client.swf').read_bytes())
        self.assertEqual((movie[:3], struct.unpack_from('<I', movie, 4)[0]), (b'FWS', len(movie)))
        for marker in [b'OpenRotMGEasyClientOptions', b'openrotmg-easy', b'easyRightClick', b'[/realm]']:
            self.assertIn(marker, movie)
        self.assertNotIn(b'AssembleeGameClientOptions', movie)
