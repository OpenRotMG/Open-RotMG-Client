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
                stack.append(obj.get(key) if isinstance(obj, dict) else getattr(obj, key))
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
                                    for name in ['clear', 'lineStyle', 'drawCircle', 'moveTo', 'lineTo']}
                        result = {'visible': True, 'graphics': graphics}
                    else: raise AssertionError(prop)
                elif prop == 'isFinite': result = math.isfinite(*values)
                elif prop == 'getTimer': result = self.now
                elif prop == 'trace': self.traces.append(values[0]); result = None
                elif prop.startswith('spectator'):
                    result = self.run('game', prop, obj, *values)
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
            with patch.object(spectator_cursor, 'add_method', capture):
                spectator.transform(movie.with_name('source-1'))

    def setUp(self):
        self.vm = CursorInstructions(self.methods)
        self.game = {'cursorAttached': False, 'cursorReady': False, 'cursorHasTick': False, 'cursorShape': None}
        self.attach()

    def attach(self, player=11, character=7):
        self.vm.run('game', 'spectatorCursorAttach', self.game, player, character)

    def parse(self, player=11, character=7, tick=1, x=2.25, y=-3.5, fire=1, body=None):
        packet = {'id_': 250}
        self.vm.run('net', 'spectatorCursorParse', packet,
                    Input(body if body is not None else struct.pack('>iiIffB', player, character, tick, x, y, fire)))
        return packet

    def consume(self, **kwargs):
        self.vm.run('game', 'spectatorCursor', self.game, self.parse(**kwargs))

    def test_exact_big_endian_packet_and_validation(self):
        packet = self.parse(tick=0xffffffff)
        self.assertEqual(packet, dict(id_=250, cursorPlayer=11, cursorCharacter=7, cursorTick=0xffffffff,
                                      cursorX=2.25, cursorY=-3.5, cursorFire=1))
        for kwargs in [dict(body=b'\0' * 20), dict(body=b'\0' * 22), dict(x=math.nan),
                       dict(y=math.inf), dict(x=-math.inf), dict(fire=2), dict(fire=255)]:
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

    def test_native_projection_fire_color_expiry_scene_and_death(self):
        projected, children = [], []
        def project(point):
            projected.append(point)
            # Nontrivial rotated/translated camera: must use native matrix, not guessed CSS scale.
            return {'x': 50 * point['y'] + 170, 'y': -50 * point['x'] + 90}
        player = {'objectId_': 11, '_-aY': 10}
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
        self.assertEqual(projected[-1], dict(x=2.25, y=-3.5, z=0))
        self.assertEqual((shape['x'], shape['y']), (-5, -22.5))
        self.assertTrue(shape['visible'])
        self.assertEqual(self.vm.lines[1], ('lineStyle', (2, 16744448, 1)))
        self.consume(tick=2, fire=0)
        draw()
        self.assertIn(('lineStyle', (2, 16777215, 1)), self.vm.lines)
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
                         [11, 7, 4, 2.25, -3.5, 295, 302.5, 1])
        count = len(self.vm.traces)
        draw()
        self.assertEqual(len(self.vm.traces), count, 'no second trace without a new cursor packet')
        self.consume(tick=5)
        self.game['spectatorFrameTime'] = self.vm.now
        draw()
        self.assertEqual(len(self.vm.traces), count, 'new packets do not bypass the1Hz trace limit')
        player['_-aY'] = 0
        self.assertFalse(draw()['visible'])
        self.assertFalse(self.game['cursorAttached'])
        self.attach()
        self.consume(tick=1)
        world['player_'] = None
        self.assertFalse(draw()['visible'])
        self.assertEqual(len(children), 1, 'one reusable native shape; no per-frame display objects')
