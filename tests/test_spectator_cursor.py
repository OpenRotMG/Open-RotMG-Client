import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_build_spectator import spectator
import spectator_cursor
import spectator_chat


class Input:
    def __init__(self, body):
        self.body, self.position = body, 0

    @property
    def bytesAvailable(self):
        return len(self.body) - self.position

    def read(self, kind):
        value, = struct.unpack_from('>' + kind, self.body, self.position)
        self.position += struct.calcsize(kind)
        return value

    def readInt(self): return self.read('i')
    def readUnsignedInt(self): return self.read('I')
    def readFloat(self): return self.read('f')
    def readUnsignedByte(self): return self.read('B')
    def readUTF(self):
        length = self.read('H')
        value = self.body[self.position:self.position + length].decode('utf-8')
        self.position += length
        return value


class CursorInstructions:
    """Execute the generated straight-line AVM subset; encoded branch validity is tested separately."""
    def __init__(self, methods):
        self.methods, self.now, self.traces, self.lines = methods, 0, [], []

    def run(self, owner, name, receiver, *args):
        lines = [line.strip() for line in self.methods[owner, name].splitlines() if line.strip()]
        labels = {line[:-1]: i for i, line in enumerate(lines) if line.endswith(':')}
        locals_, stack, pc = [receiver, *args, *([None] * 10)], [], 0
        while pc < len(lines):
            op, _, arg = lines[pc].partition(' ')
            pc += 1
            prop = re.findall(r'"([^"]*)"', arg)
            prop = prop[-1] if prop else arg
            if op in ['pushscope', 'label'] or op.endswith(':'):
                if op == 'pushscope': stack.pop()
            elif op.startswith('getlocal'):
                stack.append(locals_[int(op[8:] or arg)])
            elif op.startswith('setlocal'):
                locals_[int(op[8:] or arg)] = stack.pop()
            elif op in ['pushbyte', 'pushshort', 'pushint', 'pushuint']:
                stack.append(int(arg))
            elif op == 'pushstring': stack.append(prop)
            elif op == 'pushtrue': stack.append(True)
            elif op == 'pushfalse': stack.append(False)
            elif op == 'getproperty':
                key = stack.pop() if arg.startswith('MultinameL') else prop
                obj = stack.pop()
                stack.append(obj.get(key) if isinstance(obj, dict) else len(obj) if key == 'length' else getattr(obj, key))
            elif op == 'setproperty':
                value, obj = stack.pop(), stack.pop()
                obj[prop] = value
            elif op == 'findpropstrict': stack.append(None)
            elif op in ['callpropvoid', 'callproperty', 'constructprop']:
                count = int(arg.rsplit(',', 1)[1])
                values = stack[-count:] if count else []
                if count: del stack[-count:]
                obj = stack.pop()
                if op == 'constructprop':
                    if prop == 'Error': raise ValueError(*values)
                    if prop in ['Vector3D', 'Point']: result = dict(zip(['x', 'y', 'z'], values))
                    elif prop == 'Shape':
                        graphics = {name: (lambda *v, name=name: self.lines.append((name, v)))
                                    for name in ['clear', 'lineStyle', 'beginFill', 'endFill', 'moveTo', 'lineTo']}
                        result = {'visible': True, 'graphics': graphics}
                    else: raise AssertionError(prop)
                elif prop == 'isFinite': result = math.isfinite(*values)
                elif prop == 'getTimer': result = self.now
                elif prop == 'charAt': result = obj[values[0]:values[0] + 1]
                elif prop == 'trace': self.traces.append(values[0]); result = None
                elif prop.startswith('spectator'):
                    result = self.run('ui' if prop == 'spectatorCompose' else 'game', prop, obj, *values)
                else:
                    fn = obj[prop] if isinstance(obj, dict) else getattr(obj, prop)
                    result = fn(*values)
                if op != 'callpropvoid': stack.append(result)
            elif op == 'subtract':
                right, left = stack.pop(), stack.pop()
                stack.append(left - right)
            elif op == 'add':
                right, left = stack.pop(), stack.pop()
                stack.append(str(left) + str(right) if isinstance(left, str) or isinstance(right, str) else left + right)
            elif op == 'convert_u': stack.append(int(stack.pop()) & 0xffffffff)
            elif op in ['iftrue', 'iffalse']:
                value = bool(stack.pop())
                if value == (op == 'iftrue'): pc = labels[arg]
            elif op in ['ifeq', 'ifne', 'ifge', 'ifgt', 'ifle', 'iflt']:
                right, left = stack.pop(), stack.pop()
                take = {'ifeq': lambda: left == right, 'ifne': lambda: left != right,
                        'ifge': lambda: left >= right, 'ifgt': lambda: left > right,
                        'ifle': lambda: left <= right, 'iflt': lambda: left < right}[op]()
                if take: pc = labels[arg]
            elif op == 'jump': pc = labels[arg]
            elif op == 'returnvoid': return
            elif op == 'throw': raise ValueError(stack.pop())
            else: raise AssertionError(f'Unsupported cursor opcode {op}')


@unittest.skipUnless(os.environ.get('RABCDASM'), 'Set RABCDASM for generated native cursor tests')
class CursorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.methods = {}
        tools = Path(os.environ['RABCDASM']).resolve()
        with tempfile.TemporaryDirectory() as directory:
            movie = Path(directory) / 'source.swf'
            movie.write_bytes((spectator.ROOT / 'client.swf').read_bytes())
            subprocess.run([str(tools / 'abcexport'), str(movie)], check=True)
            subprocess.run([str(tools / 'rabcdasm'), str(movie.with_name('source-1.abc'))], check=True)
            original = spectator_cursor.add_method
            def capture(path, name, params, code, **kwargs):
                cls.methods[path.parent.name, name] = code
                original(path, name, params, code, **kwargs)
            with patch.object(spectator_cursor, 'add_method', capture), patch.object(spectator_chat, 'add_method', capture):
                spectator.transform(movie.with_name('source-1'))

    def setUp(self):
        self.vm = CursorInstructions(self.methods)
        self.chat_children = []
        self.chat = {'_-bn': {'text': ''}, 'contains': lambda field: field in self.chat_children,
                     'addChild': self.chat_children.append, 'removeChild': self.chat_children.remove, '_-KC': lambda: None}
        self.game = {'cursorAttached': False, 'cursorReady': False, 'cursorHasTick': False, 'cursorShape': None,
                     'textBox_': self.chat}
        self.attach()

    def attach(self, player=11, character=7):
        self.vm.run('game', 'spectatorCursorAttach', self.game, player, character)

    def parse(self, player=11, character=7, tick=1, x=2.25, y=-3.5, fire=1, anchor_x=1, anchor_y=-1, body=None):
        packet = {'id_': 250}
        self.vm.run('net', 'spectatorCursorParse', packet,
                    Input(body if body is not None else struct.pack('>iiIffBff', player, character, tick, x, y, fire, anchor_x, anchor_y)))
        return packet

    def consume(self, **kwargs):
        self.vm.run('game', 'spectatorCursor', self.game, self.parse(**kwargs))

    def test_exact_big_endian_packet_and_validation(self):
        packet = self.parse(tick=0xffffffff)
        self.assertEqual(packet, dict(id_=250, cursorPlayer=11, cursorCharacter=7, cursorTick=0xffffffff,
                                      cursorX=2.25, cursorY=-3.5, cursorFire=1, cursorAnchorX=1, cursorAnchorY=-1))
        for kwargs in [dict(body=b'\0' * 21), dict(body=b'\0' * 28), dict(body=b'\0' * 30), dict(x=math.nan),
                       dict(y=math.inf), dict(x=-math.inf), dict(anchor_x=math.inf), dict(anchor_y=math.nan),
                       dict(fire=2), dict(fire=255)]:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'Invalid spectator cursor'):
                self.parse(**kwargs)
            self.assertIn('Invalid cursor packet250', self.vm.traces[-1])
        self.assertEqual(self.parse(fire=0)['cursorFire'], 0)

    def test_identity_attach_and_resets(self):
        self.consume()
        self.assertTrue(self.game['cursorReady'])
        self.attach(character=8)
        self.assertFalse(self.game['cursorReady'])
        self.consume(character=7)
        self.assertFalse(self.game['cursorAttached'])
        self.assertIn('identity mismatch', self.vm.traces[-1])
        self.attach(player=12)
        self.consume(player=11)
        self.assertFalse(self.game['cursorReady'])
        self.vm.run('game', 'spectatorCursorReset', self.game)
        self.consume(player=12)
        self.assertFalse(self.game['cursorAttached'])

    def test_unsigned_order_wrap_duplicate_and_stale_cannot_reseed(self):
        self.consume(tick=0xfffffffe)
        self.consume(tick=0xffffffff)
        self.consume(tick=0)
        self.assertTrue(self.game['cursorReady'])
        self.consume(tick=0)
        self.assertFalse(self.game['cursorReady'])
        self.assertIn('Stale cursor tick', self.vm.traces[-1])
        self.consume(tick=0xffffffff)
        self.assertFalse(self.game['cursorReady'])
        self.consume(tick=1)
        self.assertTrue(self.game['cursorReady'])

    def test_view_anchored_arrow_projection_expiry_scene_and_death(self):
        projected, children = [], []
        def project(point):
            projected.append(point)
            # Nontrivial rotated/translated camera: must use native matrix, not guessed CSS scale.
            return {'x': 50 * point['y'] + 170, 'y': -50 * point['x'] + 90}
        player = {'objectId_': 11, '_-aY': 10, 'x_': 1.5, 'y_': -0.5}
        world = {'player_': player, 'goDict_': {11: player}, 'addChild': children.append,
                 'localToGlobal': lambda point: {'x': point['x'] + 300, 'y': point['y'] + 325}}
        player['map_'] = world
        self.game.update(map_=world, spectatorFrameTime=0,
                         **{'_-on': {'wToS_': {'transformVector': project},
                                     '_-FL': {'contains': lambda x, y: -300 <= x < 300 and -325 <= y < 275}}})
        def draw():
            # onEnterFrame hides before any conditional draw.
            if self.game['cursorShape']: self.game['cursorShape']['visible'] = False
            self.vm.run('game', 'spectatorCursorDraw', self.game, self.vm.now)
            return self.game['cursorShape']
        self.consume()
        shape = draw()
        self.assertEqual(projected[-1], dict(x=2.75, y=-3, z=0))
        self.assertEqual((shape['x'], shape['y']), (20, -47.5))
        self.assertTrue(shape['visible'])
        self.assertEqual(self.vm.lines[1], ('lineStyle', (1, 0, 1)))
        self.assertIn(('beginFill', (16777215, 1)), self.vm.lines)
        self.assertIn(('lineTo', (0, 18)), self.vm.lines)
        self.assertNotIn('drawCircle', [name for name, _ in self.vm.lines])
        self.consume(tick=2, fire=0)
        draw()
        self.assertIn(('lineStyle', (1, 0, 1)), self.vm.lines)
        self.vm.now = 999
        self.assertTrue(draw()['visible'])
        self.vm.now = 1000
        self.assertFalse(draw()['visible'])
        self.consume(tick=3, x=1000)
        self.assertFalse(draw()['visible'])
        self.consume(tick=4)
        self.assertTrue(draw()['visible'])
        self.assertTrue(self.vm.traces[-1].startswith('openrotmg-spectator:cursor:'))
        self.assertEqual(list(map(float, self.vm.traces[-1].split(':')[2:])),
                         [11, 7, 4, 2.25, -3.5, 320, 277.5, 1])
        count = len(self.vm.traces)
        draw()
        self.assertEqual(len(self.vm.traces), count, 'no second trace without a new cursor packet')
        self.consume(tick=5)
        self.game['spectatorFrameTime'] = self.vm.now
        draw()
        self.assertEqual(len(self.vm.traces), count, 'new packets do not bypass the1Hz trace limit')
        self.vm.now = 2147483640
        self.consume(tick=6)
        self.vm.now = -2147482657
        self.assertTrue(draw()['visible'], '999ms after signed timer wrap')
        self.vm.now = -2147482656
        self.assertFalse(draw()['visible'], 'expires at1000ms across signed timer wrap')
        self.consume(tick=7)
        player['_-aY'] = 0
        self.assertFalse(draw()['visible'])
        self.assertFalse(self.game['cursorAttached'])
        self.attach()
        self.consume(tick=1)
        world['player_'] = None
        self.assertFalse(draw()['visible'])
        self.assertEqual(len(children), 1, 'one reusable native shape; no per-frame display objects')

    def chat_packet(self, phase=1, draft='', tick=1, player=11, character=7, body=None):
        text = draft.encode('utf-8')
        packet = {'id_': 251}
        self.vm.run('net', 'spectatorChatParse', packet, Input(body if body is not None else
                    struct.pack('>iiIBH', player, character, tick, phase, len(text)) + text))
        return packet

    def test_native_chat_opens_types_pastes_and_closes_without_viewer_input(self):
        for tick, phase, text in [(1, 1, ''), (2, 1, 'w'), (3, 1, 'wt'), (4, 2, 'wts spd')]:
            self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(tick=tick, phase=phase, draft=text))
            self.assertEqual(self.chat['_-bn']['text'], text)
            self.assertEqual(self.chat['_-bn']['type'], 'dynamic')
            self.assertFalse(self.chat['_-bn']['selectable'])
            self.assertEqual(len(self.chat_children), 1)
            self.vm.run('game', 'spectatorChatDraw', self.game, self.vm.now)
            self.assertEqual(self.vm.traces[-1], f'openrotmg-spectator:compose:11:7:{tick}:{phase}:{text}')
        count = len(self.vm.traces)
        self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(tick=5, phase=2, draft='wts spd'))
        self.vm.run('game', 'spectatorChatDraw', self.game, self.vm.now)
        self.assertEqual(len(self.vm.traces), count, 'unchanged heartbeat does not spam draft traces')
        self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(tick=6, phase=0))
        self.assertEqual(self.chat_children, [])
        self.assertEqual(self.chat['_-bn']['text'], '')
        code = self.methods['ui', 'spectatorCompose']
        self.assertNotIn('focus', code)
        self.assertNotIn('_-Ck', code)
        self.assertNotIn('gsc_', code)

    def test_chat_invalid_wire_identity_order_expiry_and_resets(self):
        for kwargs in [dict(body=b'\0' * 14), dict(body=b'\0' * 528), dict(phase=3),
                       dict(phase=0, draft='not closed'), dict(draft='/tell private'), dict(draft='x' * 257)]:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'Invalid spectator composition'):
                self.chat_packet(**kwargs)
        self.vm.now = 2147483640
        self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(tick=0xffffffff, draft='wts'))
        self.vm.now = -2147482657
        self.vm.run('game', 'spectatorChatExpire', self.game)
        self.assertTrue(self.chat_children)
        self.vm.now += 1
        self.vm.run('game', 'spectatorChatExpire', self.game)
        self.assertFalse(self.chat_children)
        self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(tick=0, draft='next'))
        self.assertTrue(self.chat_children)
        self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(tick=0, draft='duplicate'))
        self.assertFalse(self.chat_children)
        self.assertIn('Stale composition tick', self.vm.traces[-1])
        self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(tick=1, player=12, draft='wrong'))
        self.assertFalse(self.game['cursorAttached'])
        self.assertFalse(self.chat_children)
        self.assertIn('identity mismatch', self.vm.traces[-1])
        self.attach()
        self.vm.run('game', 'spectatorChat', self.game, self.chat_packet(draft='wts'))
        self.attach(character=8)
        self.assertFalse(self.chat_children)

    def test_cursor_offset_ignores_native_server_pose_skew(self):
        player = {'objectId_': 11, '_-aY': 10, 'x_': 90, 'y_': 190}
        world = {'player_': player, 'goDict_': {11: player}, 'addChild': lambda shape: None,
                 'localToGlobal': lambda point: point}
        player['map_'] = world
        camera = {'transformVector': lambda p: {'x': (p['x'] - player['x_']) * 50,
                                               'y': (p['y'] - player['y_']) * 50}}
        self.game.update(map_=world, spectatorFrameTime=0,
                         **{'_-on': {'wToS_': camera, '_-FL': {'contains': lambda x, y: True}}})
        for tick, native_x, native_y, anchor_x, anchor_y in [(1, 90, 190, 100, 200), (2, 90.5, 190.5, 110, 220)]:
            player.update(x_=native_x, y_=native_y)
            self.consume(tick=tick, x=anchor_x + 2, y=anchor_y + 3, anchor_x=anchor_x, anchor_y=anchor_y)
            self.vm.run('game', 'spectatorCursorDraw', self.game, self.vm.now)
            self.assertEqual((self.game['cursorShape']['x'], self.game['cursorShape']['y']), (100, 150))
