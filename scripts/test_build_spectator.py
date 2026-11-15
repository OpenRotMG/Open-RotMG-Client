import hashlib
import os
import re
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_spectator as spectator


def tags(movie):
    movie = movie if movie[:3] == b'FWS' else b'FWS' + movie[3:8] + zlib.decompress(movie[8:])
    if struct.unpack_from('<I', movie, 4)[0] != len(movie):
        raise AssertionError('Invalid SWF length')
    bits = movie[8] >> 3
    position = 8 + (5 + 4 * bits + 7) // 8 + 4
    result = []
    while position < len(movie):
        header, = struct.unpack_from('<H', movie, position)
        position += 2
        kind, size = header >> 6, header & 63
        if size == 63:
            size, = struct.unpack_from('<I', movie, position)
            position += 4
        result.append((kind, movie[position:position + size]))
        position += size
    return result


def interaction_bytecode(data):
    """Read encoded interaction bodies, independently of assembler label rendering."""
    position = 4
    def u8():
        nonlocal position
        value = data[position]
        position += 1
        return value
    def uint():
        value = shift = 0
        while True:
            byte = u8()
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7
    def many(n):
        return [uint() for _ in range(n)]
    for _ in range(2):
        many(max(0, uint() - 1))
    doubles = uint()
    position += max(0, doubles - 1) * 8
    strings = ['']
    for _ in range(uint() - 1):
        size = uint()
        strings.append(data[position:position + size].decode('utf8'))
        position += size
    for _ in range(uint() - 1):
        u8(); uint()
    for _ in range(uint() - 1):
        many(uint())
    names = ['']
    for _ in range(uint() - 1):
        kind = u8()
        if kind in (7, 13, 9, 14):
            first, second = many(2)
            names.append(strings[second if kind in (7, 13) else first])
        elif kind in (15, 16, 27, 28):
            value = uint()
            names.append(strings[value] if kind in (15, 16) else '')
        elif kind in (17, 18):
            names.append('')
        elif kind == 29:
            uint(); many(uint()); names.append('')
        else:
            raise AssertionError(f'Unknown multiname {kind}')
    for _ in range(uint()):
        params = uint()
        many(params + 2)
        flags = u8()
        if flags & 8:
            for _ in range(uint()):
                uint(); u8()
        if flags & 128:
            many(params)
    for _ in range(uint()):
        uint(); many(uint() * 2)
    methods = {}
    def traits():
        for _ in range(uint()):
            name, flags = names[uint()], u8()
            kind = flags & 15
            if kind in (0, 6):
                many(2)
                if uint():
                    u8()
            elif kind in (1, 2, 3):
                uint()
                method = uint()
                if name.startswith('spectator') or (class_name == 'GameSprite' and name == 'onEnterFrame'):
                    methods[method] = name
            elif kind in (4, 5):
                many(2)
            else:
                raise AssertionError(f'Unknown trait {kind}')
            if flags & 64:
                many(uint())
    classes = uint()
    class_name = ''
    for _ in range(classes):
        name = names[uint()]
        class_name = name
        uint()
        if u8() & 8:
            uint()
        many(uint())
        init = uint()
        if name == '_-06M':
            methods[init] = name + ':init'
        traits()
    class_name = ''
    for _ in range(classes):
        uint(); traits()
    for _ in range(uint()):
        uint(); traits()
    result = []
    for _ in range(uint()):
        method = uint()
        many(4)
        length = uint()
        code = data[position:position + length]
        position += length
        if method in methods:
            result.append((methods[method], code))
        for _ in range(uint()):
            many(5)
        traits()
    return result


def encoded_branches(code):
    position, starts, branches = 0, set(), []
    single = {3, 9, 0x20, 0x26, 0x27, 0x30, 0x47, 0x48, 0x74, 0x90, 0xa0, 0xa1, 0xa2, 0xa7, 0xab, 0xaf, *range(0xd0, 0xd8)}
    operands = {op: 1 for op in [0x25, 0x2c, 0x2d, 0x2e, 0x42, 0x49, 0x55, 0x5d, 0x5e, 0x60, 0x61, 0x62, 0x63, 0x66, 0x68, 0x80, 0x86, 0xb2, 0xc2, 0xc3]}
    operands.update({0x46: 2, 0x4a: 2, 0x4f: 2})
    while position < len(code):
        start = position
        starts.add(start)
        op = code[position]
        position += 1
        if 0x0c <= op <= 0x1a:
            offset = int.from_bytes(code[position:position + 3], 'little', signed=True)
            position += 3
            branches.append((start, position + offset))
        elif op == 0x24:
            position += 1
        elif op in operands:
            for _ in range(operands[op]):
                while code[position] & 128:
                    position += 1
                position += 1
        else:
            assert op in single, f'Unexpected interaction opcode {op:#x} at {start}'
    assert position == len(code)
    for source, target in branches:
        assert target in starts, f'Branch {source}->{target} is not an instruction boundary'
        assert target > source or code[target] == 9, f'Backward branch {source}->{target} does not target AVM2 label'
    return branches


class SpectatorBuildTests(unittest.TestCase):
    def test_pinned_movie_changes_only_game_abc_preserving_assets_and_reference(self):
        source = (spectator.ROOT / 'client.swf').read_bytes()
        output = (spectator.ROOT / 'spectator.swf').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), spectator.SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(output).hexdigest(), spectator.LOCK['outputSha256'])
        self.assertEqual(len(output), spectator.LOCK['outputBytes'])
        before, after = tags(source), tags(output)
        self.assertEqual(len(before), len(after))
        changed = [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
        self.assertEqual(len(changed), 1)
        self.assertEqual(before[changed[0]][0], 82)  # DoABC
        abc = [payload for kind, payload in before if kind == 82]
        self.assertEqual(len(abc), 2)
        self.assertEqual(before[changed[0]][1], abc[1])

    def test_encoded_backward_branch_requires_label_not_merely_instruction_boundary(self):
        with self.assertRaisesRegex(AssertionError, 'does not target AVM2 label'):
            encoded_branches(bytes.fromhex('d3 10 fb ff ff'))
        self.assertEqual(encoded_branches(bytes.fromhex('09 d3 10 fa ff ff')), [(2, 0)])

    def test_unknown_source_rejected_before_tools_or_artifact_write(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(spectator, 'ROOT', Path(directory)):
            (spectator.ROOT / 'client.swf').write_bytes(b'unknown movie')
            target = spectator.ROOT / 'spectator.swf'
            target.write_bytes(b'existing evidence')
            with self.assertRaisesRegex(RuntimeError, 'unchanged pinned'):
                spectator.build(Path('/missing-tools'))
            self.assertEqual(target.read_bytes(), b'existing evidence')

    @unittest.skipUnless(os.environ.get('RABCDASM'), 'Set RABCDASM for native assembly/reproducibility tests')
    def test_reproducible_assembly_and_exact_bootstrap_action_boundaries(self):
        tools = Path(os.environ['RABCDASM']).resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = (spectator.ROOT / 'client.swf').read_bytes()
            (root / 'client.swf').write_bytes(source)
            with patch.object(spectator, 'ROOT', root):
                spectator.build(tools)
                first = (root / 'spectator.swf').read_bytes()
                spectator.build(tools)
                self.assertEqual((root / 'spectator.swf').read_bytes(), first)
                self.assertEqual((root / 'client.swf').read_bytes(), source)
            subprocess.run([str(tools / 'abcexport'), str(root / 'spectator.swf')], check=True)
            subprocess.run([str(tools / 'rabcdasm'), str(root / 'spectator-1.abc')], check=True)
            bodies = interaction_bytecode((root / 'spectator-1.abc').read_bytes())
            self.assertTrue({'spectatorCursorParse', 'spectatorCursor', 'spectatorCursorDraw',
                             'spectatorCursorAttach', 'spectatorCursorReset', 'spectatorChatParse',
                             'spectatorChat', 'spectatorChatDraw', 'spectatorChatReset',
                             'spectatorChatExpire', 'spectatorCompose'}.issubset({name for name, _ in bodies}))
            for name, code in bodies:
                with self.subTest(encoded_method=name):
                    encoded_branches(code)
            abc = root / 'spectator-1'
            web = (abc / 'WebMain.class.asasm').read_text()
            self.assertIn('"spectatorConnect"', web)
            self.assertIn('"spectatorBlockInput"', web)
            self.assertIn('pushstring          "mouseDown"', web)
            self.assertNotIn('pushstring          "mouseMove"', web)
            self.assertNotIn('pushstring          "mouseOver"', web)
            net = (abc / 'com/company/assembleegameclient/net/_-1f.class.asasm').read_text()
            tick_start = net.index('  trait method ' + spectator.private('_-02H', spectator.NET + ':_-1f#0'))
            tick = net[tick_start:net.index('  end ; trait', tick_start)]
            self.assertIn('"tickTime_"', tick)
            self.assertIn('"tickId_"', tick)
            self.assertIn('pushshort           250', net)
            self.assertIn(spectator.q('spectatorCursor'), net)
            packet = (abc / 'com/company/net/_-098.class.asasm').read_text()
            self.assertIn('pushshort           251', net)
            self.assertIn(spectator.q('spectatorChat'), net)
            self.assertIn('pushbyte            29', packet)
            self.assertIn('pushbyte            15', packet)
            for field in ['readInt', 'readUnsignedInt', 'readFloat', 'readUnsignedByte', 'readUTF', 'isFinite']:
                self.assertIn(spectator.q(field), packet)
            self.assertIn('openrotmg-spectator:tick:', tick)
            self.assertIn(spectator.q('gs_'), tick)
            self.assertIn(spectator.q('spectatorSource'), tick)
            notification_start = net.index('  trait method ' + spectator.private('_-Lx', spectator.NET + ':_-1f#0'))
            notification = net[notification_start:net.index('  end ; trait', notification_start)]
            self.assertNotIn('openrotmg-spectator:tick:', notification)
            game = (abc / 'com/company/assembleegameclient/game/GameSprite.class.asasm').read_text()
            self.assertNotIn('getproperty         ' + spectator.q('credits_'), game)
            nearby = (abc / '_-Rv/_-QV.class.asasm').read_text()
            draw_start = nearby.index('  trait method ' + spectator.q('draw'))
            draw = nearby[draw_start:nearby.index('  end ; trait', draw_start)]
            self.assertIn('getproperty         ' + spectator.q('_-VD'), draw)
            self.assertIn('callpropvoid        ' + spectator.q('draw'), draw)
            self.assertNotIn('callproperty', draw)
            self.assertNotIn('constructprop', draw)
            self.assertNotIn(spectator.q('goDict_'), draw)
            self.assertNotIn(spectator.q('_-Cs'), draw)
            start = net.index('  trait method ' + spectator.private('_-ux', spectator.NET + ':_-1f#0'))
            hello = net[start:net.index('  end ; trait', start)]
            self.assertNotIn('"Account"', hello)
            self.assertIn('"spectator"', hello)
            chars = (abc / 'com/company/assembleegameclient/appengine/_-0KR.class.asasm').read_text()
            constructor = chars[chars.index('  iinit'):chars.index('  end ; method')]
            self.assertNotIn('"Account"', constructor)
            self.assertNotIn('"XML"', constructor)
            connection = (abc / 'com/company/net/ServerConnection.class.asasm').read_text()
            start = connection.index('  trait method ' + spectator.q('_-hb'))
            send = connection[start:connection.index('  end ; trait', start)]
            self.assertEqual(send.count('getproperty         ' + spectator.q('id_')), 6)
            self.assertIn('returnvoid', send)
            self.assertEqual([int(x) for x in re.findall(r'pushbyte\s+(\d+)', send)[:6]], [17, 45, 16, 22, 14, 11])

            def method(path, name):
                text = (abc / path).read_text()
                start = re.search(r'(?m)^  trait method [^\n]*, "' + re.escape(name) + r'"\)', text).start()
                return text[start:text.index('  end ; trait', start)]

            bind = method('com/company/assembleegameclient/game/GameSprite.class.asasm', 'spectatorBind')
            self.assertIn('getproperty         ' + spectator.q('charList_'), bind)
            self.assertIn('getproperty         ' + spectator.q('name_'), bind)
            self.assertLess(bind.index('setproperty         ' + spectator.q('name_')), bind.index('ifeq'))
            frame = method('com/company/assembleegameclient/game/GameSprite.class.asasm', 'onEnterFrame')
            self.assertLess(frame.index(spectator.q('spectatorBind')), frame.index(spectator.q('_-V1')))
            self.assertIn('openrotmg-spectator:frame:', frame)
            self.assertIn(spectator.q('spectatorSource'), frame[frame.index('openrotmg-spectator:frame:'):])
            net_path = 'com/company/assembleegameclient/net/_-1f.class.asasm'
            game_path = 'com/company/assembleegameclient/game/GameSprite.class.asasm'
            attach = method(net_path, '_-cw')
            for field in ['objectId_', 'charId_', 'spectatorCursorAttach']:
                self.assertIn(spectator.q(field), attach)
            for name in ['_-ju', '_-X3', '_-038', '_-of', 'onError', '_-nc']:
                self.assertIn(spectator.q('spectatorCursorReset'), method(net_path, name))
            self.assertIn(spectator.q('spectatorCursorReset'), method(game_path, 'onRemovedFromStage'))
            cursor = method(game_path, 'spectatorCursorDraw')
            self.assertNotIn(spectator.q('drawCircle'), cursor)
            for field in ['wToS_', 'transformVector', '_-FL', 'contains', 'beginFill', 'endFill', 'lineTo',
                          'lineStyle', 'goDict_', '_-aY', 'cursorAnchorX', 'cursorAnchorY']:
                self.assertIn(spectator.q(field), cursor)
            self.assertNotIn(spectator.q('angleRad_'), cursor)
            self.assertIn('openrotmg-spectator:cursor', cursor)
            self.assertIn(spectator.q('localToGlobal'), cursor)
            self.assertIn(spectator.q('cursorTracePending'), cursor)
            self.assertIn('pushshort           1000', cursor)
            initialize = method('com/company/assembleegameclient/game/GameSprite.class.asasm', 'initialize')
            self.assertNotIn(spectator.q('mui_'), initialize)
            for path, name in [('com/company/assembleegameclient/net/_-1f.class.asasm', 'move'),
                               ('com/company/assembleegameclient/objects/Player.class.asasm', 'shoot')]:
                self.assertNotIn('callprop', method(path, name))
            controller = method('com/company/assembleegameclient/game/_-07a.class.asasm', 'onAddedToStage')
            self.assertNotIn('addEventListener', controller)
            block = method('WebMain.class.asasm', 'spectatorBlockInput')
            self.assertIn(spectator.q('spectatorInput'), block)
            for name in ['preventDefault', 'stopImmediatePropagation']:
                self.assertIn('callpropvoid        ' + spectator.q(name), block)
            control = method('com/company/assembleegameclient/game/GameSprite.class.asasm', 'spectatorInput')
            self.assertIn('pushstring          "mouseDown"', control)
            self.assertIn('pushstring          "rightMouseDown"', control)
            self.assertEqual(control.count('getlocal            5'), 4)
            self.assertIn(spectator.q('_-gV', 'com.company.assembleegameclient.ui'), control)
            self.assertIn(spectator.q('_-w6', '_-Rv'), control)
            self.assertIn(spectator.q('spectatorInspect'), control)
            for name in ['shoot', 'teleportTo', 'useItem', 'move', 'initialize', 'requestTrade', 'dispatchEvent']:
                self.assertNotIn(spectator.q(name), control)
            inspect = method('com/company/assembleegameclient/game/GameSprite.class.asasm', 'spectatorInspect')
            self.assertIn('openrotmg-spectator:inspect:', inspect)
            for name in ['spectatorBind', 'goDict_', 'objectId_', 'stageX', 'stageY']:
                self.assertIn(spectator.q(name), inspect)
            for name in ['name_', 'objectType_', 'Account', 'guid_']:
                self.assertNotIn(spectator.q(name), inspect)
            zoom = method('com/company/assembleegameclient/ui/_-ej.class.asasm', 'spectatorInput')
            for name in ['_-Kr', '_-w-', 'draw', 'spectatorInspect']:
                self.assertIn(spectator.q(name), zoom)
            self.assertIn('pushstring          "mouseWheel"', zoom)
            minimap = (abc / 'com/company/assembleegameclient/ui/_-ej.class.asasm').read_text()
            self.assertIn('pushint             16776960', minimap)  # Existing normal-player yellow dots.
            world = method('com/company/assembleegameclient/map/_-Xl.class.asasm', 'spectatorPlayer')
            self.assertIn(spectator.q('_-u2'), world)
            self.assertIn(spectator.q('_-1D'), world)
            self.assertIn(spectator.q('spectatorHit'), world)
            hit = method('com/company/assembleegameclient/objects/GameObject.class.asasm', 'spectatorHit')
            self.assertIn('QName(ProtectedNamespace("_-iP"), "vS_")', hit)
            chat = method('com/company/assembleegameclient/ui/_-4D.class.asasm', 'spectatorPlayer')
            for name in ['userData', 'spectatorActor', 'recipient_', 'spectatorNameWidth', 'globalToLocal', 'ascent', 'descent']:
                self.assertIn(spectator.q(name), chat)
            self.assertNotIn(spectator.q('getAtomIndexAtPoint'), chat)
            name = method('com/company/assembleegameclient/ui/_-0At.class.asasm', 'spectatorName')
            for field in ['textWidth', 'createTextLine', 'spectatorNameWidth']:
                self.assertIn(spectator.q(field), name)
            self.assertIn('initscopedepth 4', name)
            self.assertIn('initscopedepth 5', hit)
            self.assertNotIn(spectator.q('addChild'), name)
            for menu in ['_-02p', '_-06M']:
                text = (abc / f'_-0DB/{menu}.class.asasm').read_text()
                constructor = text[text.index('  iinit'):text.index('  end ; method')]
                for action in ['teleportTo', 'requestTrade', 'Account', '_-Kh', '_-0KG']:
                    self.assertNotIn(spectator.q(action), constructor)
                self.assertIn(spectator.q('_-gV', 'com.company.assembleegameclient.ui'), constructor)


if __name__ == '__main__':
    unittest.main()
