"""Derive spectator.swf from the pinned, otherwise immutable 123.5.1 movie.

Usage: python3 scripts/build_spectator.py /path/to/RABCDAsm
Only small method transforms live here; disassembly stays in a temporary directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'spectator/lock.json').read_text())
SOURCE_SHA256 = LOCK['sourceSha256']
GAME = 'com.company.assembleegameclient.game'
NET = 'com.company.assembleegameclient.net'
OBJECTS = 'com.company.assembleegameclient.objects'
PARAMETERS = 'com.company.assembleegameclient.parameters'
APP = 'com.company.assembleegameclient.appengine'


def q(name, package=''):
    return f'QName(PackageNamespace("{package}"), "{name}")'


def private(name, owner):
    return f'QName(PrivateNamespace("*", "{owner}"), "{name}")'


def instructions(code):
    return ''.join('      ' + line.strip() + '\n' for line in code.strip().splitlines() if line.strip())


def replace_method(path, name, code, prefix=False, suffix=False, constructor=False):
    text = path.read_text()
    pattern = r'(?ms)^  iinit\n.*?^  end ; method' if constructor else r'(?ms)^  trait method [^\n]+\n.*?^  end ; trait'
    matches = [m for m in re.finditer(pattern, text) if constructor or re.search(r', "' + re.escape(name) + r'"\)(?: flag .*)?$', m.group().splitlines()[0])]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one method {path}:{name}, got {len(matches)}')
    match = matches[0]
    body = match.group()
    if prefix:
        body = body.replace('     code\n', '     code\n' + instructions(code), 1)
    elif suffix:
        position = body.rfind('      returnvoid')
        if position < 0:
            raise RuntimeError(f'Expected returnvoid in {path}:{name}')
        body = body[:position] + instructions(code) + body[position:]
    else:
        body = re.sub(r'(?ms)( {4,5}code\n).*?( {4,5}end ; code)', lambda m: m[1] + instructions(code) + m[2], body, count=1)
    # Added bootstrap/interception code can need more stack than the original method.
    body = re.sub(r'maxstack \d+', 'maxstack 24', body)
    path.write_text(text[:match.start()] + body + text[match.end():])


def add_method(path, name, params, code, locals_=2):
    text = path.read_text()
    body = f'''  trait method {q(name)}
   method
    refid "spectator/{name}"
{''.join('    param ' + p + chr(10) for p in params)}    returns {q('void')}
    body
     maxstack 24
     localcount {locals_}
     initscopedepth 9
     maxscopedepth 10
     code
{instructions(code)}     end ; code
    end ; body
   end ; method
  end ; trait
'''
    marker = ' end ; instance'
    if text.count(marker) != 1:
        raise RuntimeError(f'Expected one instance in {path}')
    path.write_text(text.replace(marker, body + marker))


def status(state, error=''):
    return f'''findpropstrict {q('trace')}
    pushstring "openrotmg-spectator:{state}:{error}"
    callpropvoid {q('trace')}, 1'''


def transform(root):
    web = root / 'WebMain.class.asasm'
    network = root / 'com/company/assembleegameclient/net/_-1f.class.asasm'
    game = root / 'com/company/assembleegameclient/game/GameSprite.class.asasm'
    player = root / 'com/company/assembleegameclient/objects/Player.class.asasm'
    objects = root / 'com/company/assembleegameclient/objects/GameObject.class.asasm'
    connection = root / 'com/company/net/ServerConnection.class.asasm'
    chars = root / 'com/company/assembleegameclient/appengine/_-0KR.class.asasm'
    net_private = lambda name: private(name, NET + ':_-1f#0')
    game_private = lambda name: private(name, GAME + ':GameSprite/instance')
    bot = f'''getlex {q('Parameters', PARAMETERS)}
    getproperty {q('root')}
    getproperty {q('loaderInfo')}
    getproperty {q('parameters')}
    getproperty {q('bot')}'''

    # Bypass the account/menu dependency graph entirely, not a simulated account response.
    replace_method(web, 'setup', f'''getlocal0
    pushscope
    getlex {q('Parameters', PARAMETERS)}
    getlocal0
    getproperty {q('stage')}
    getproperty {q('root')}
    setproperty {q('root')}
    getlocal0
    getproperty {q('stage')}
    pushstring "exactFit"
    setproperty {q('scaleMode')}
    findpropstrict {q('loadEmbeds', 'com.company.assembleegameclient.util')}
    callpropvoid {q('loadEmbeds', 'com.company.assembleegameclient.util')}, 0
    getlocal0
    pushnull
    callpropvoid {q('spectatorConnect')}, 1
    returnvoid''')
    add_method(web, 'spectatorConnect', [q('Event', 'flash.events')], f'''getlocal0
    pushscope
    {status('connecting')}
    getlocal1
    iffalse initial
    getlocal0
    getlocal1
    getproperty {q('target')}
    callpropvoid {q('removeChild')}, 1
    getlocal1
    getproperty {q('target')}
    callpropvoid {q('dispose')}, 0
    initial:
    findpropstrict {q('GameSprite', GAME)}
    findpropstrict {q('Server', NET)}
    pushstring "Spectator"
    pushstring "127.0.0.1"
    pushshort 2050
    constructprop {q('Server', NET)}, 3
    pushbyte -2
    pushfalse
    pushbyte 1
    pushbyte -1
    pushnull
    findpropstrict {q('_-0KR', APP)}
    {bot}
    constructprop {q('_-0KR', APP)}, 1
    pushnull
    constructprop {q('GameSprite', GAME)}, 8
    setlocal2
    getlocal2
    getlex {q('_-j-', '_-9R')}
    getproperty {q('RECONNECT')}
    getlocal0
    getproperty {q('spectatorConnect')}
    callpropvoid {q('addEventListener')}, 2
    getlocal0
    getlocal2
    callpropvoid {q('addChild')}, 1
    returnvoid''', locals_=3)

    # Native hover remains intact; capture action events before any HUD prediction or drag.
    events = ['mouseDown', 'mouseUp', 'click', 'doubleClick', 'rightMouseDown', 'rightMouseUp',
              'rightClick', 'middleMouseDown', 'middleMouseUp', 'middleClick', 'mouseWheel',
              'keyDown', 'keyUp', 'textInput', 'touchBegin', 'touchEnd', 'touchTap']
    capture = ''
    for event in events:
        for use_capture in ['pushtrue', 'pushfalse']:
            capture += f'''getlocal0
            getproperty {q('stage')}
            pushstring "{event}"
            getlocal0
            getproperty {q('spectatorBlockInput')}
            {use_capture}
            pushint 2147483647
            callpropvoid {q('addEventListener')}, 4\n'''
    replace_method(web, 'setup', capture, prefix=True)
    add_method(web, 'spectatorBlockInput', [q('Event', 'flash.events')], f'''getlocal0
    pushscope
    getlocal1
    callpropvoid {q('preventDefault')}, 0
    getlocal1
    callpropvoid {q('stopImmediatePropagation')}, 0
    returnvoid''')

    # The native HUD only needs public display metadata; never load or create an account.
    replace_method(chars, '', f'''getlocal0
    pushscope
    getlocal0
    pushstring "SAVED_CHARS_LIST"
    constructsuper 1
    getlocal0
    getlocal1
    setproperty {q('name_')}
    getlocal0
    pushtrue
    setproperty {q('_-hv')}
    getlocal0
    newobject 0
    setproperty {q('charStats_')}
    returnvoid''', constructor=True)
    replace_method(network, '_-ux', f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('_-08')}
    pushbyte 17
    callproperty {q('_-YE')}, 1
    coerce {q('_-0By', '_-0Ag')}
    setlocal2
    getlocal2
    getlex {q('Parameters', PARAMETERS)}
    getproperty {q('_-0AG')}
    setproperty {q('buildVersion_')}
    getlocal2
    getlocal0
    getproperty {q('gameId_')}
    setproperty {q('gameId_')}
    getlocal2
    pushstring "spectator"
    setproperty {q('guid_')}
    getlocal2
    pushstring ""
    setproperty {q('password_')}
    getlocal2
    pushstring ""
    setproperty {q('secret_')}
    getlocal2
    pushbyte -1
    setproperty {q('keyTime_')}
    getlocal2
    pushstring ""
    setproperty {q('_-2B')}
    getlocal2
    getproperty {q('key_')}
    pushbyte 0
    setproperty {q('length')}
    getlocal0
    getproperty {q('_-08')}
    getlocal2
    callpropvoid {q('_-hb')}, 1
    returnvoid''')
    replace_method(network, '_-sM', 'getlocal0\npushscope\nreturnvoid')
    replace_method(game, '_-dO', 'getlocal0\npushscope\nreturnvoid')
    replace_method(game, 'initialize', f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('map_')}
    callpropvoid {q('initialize')}, 0
    getlocal0
    getproperty {q('_-V1')}
    callpropvoid {q('initialize')}, 0
    getlocal0
    findpropstrict {q('_-0Bv', 'com.company.assembleegameclient.ui')}
    getlocal0
    constructprop {q('_-0Bv', 'com.company.assembleegameclient.ui')}, 1
    setproperty {q('_-Ht')}
    getlocal0
    getproperty {q('_-Ht')}
    pushshort 594
    setproperty {q('x')}
    getlocal0
    getlocal0
    getproperty {q('_-Ht')}
    callpropvoid {q('addChild')}, 1
    returnvoid''')
    # Public spectator scenes never need account/guild badges or the inactivity controller.
    replace_method(game, 'onAddedToStage', f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('_-V1')}
    pushshort 600
    setproperty {q('x')}
    getlocal0
    getproperty {q('gsc_')}
    callpropvoid {q('connect')}, 0
    getlocal0
    findpropstrict {q('getTimer', 'flash.utils')}
    callproperty {q('getTimer', 'flash.utils')}, 0
    setproperty {q('lastUpdate_')}
    getlocal0
    getproperty {q('stage')}
    pushstring "enterFrame"
    getlocal0
    getproperty {game_private('onEnterFrame')}
    callpropvoid {q('addEventListener')}, 2
    returnvoid''')
    replace_method(game, 'onRemovedFromStage', f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('gsc_')}
    getproperty {q('_-08')}
    callpropvoid {q('_-0FG')}, 0
    getlocal0
    getproperty {q('stage')}
    pushstring "enterFrame"
    getlocal0
    getproperty {game_private('onEnterFrame')}
    callpropvoid {q('removeEventListener')}, 2
    returnvoid''')
    # Keep native drawing, but not the playable frame's analytics or input bookkeeping.
    game.write_text(game.read_text().replace(' end ; instance',
        f'  trait slot {q("spectatorFrameTime")} type {q("int")} value Integer(0) end\n end ; instance'))
    replace_method(game, 'onEnterFrame', f'''getlocal0
    pushscope
    findpropstrict {q('getTimer', 'flash.utils')}
    callproperty {q('getTimer', 'flash.utils')}, 0
    setlocal2
    getlocal2
    getlocal0
    getproperty {q('lastUpdate_')}
    subtract
    setlocal3
    getlocal0
    getproperty {q('map_')}
    getlocal2
    getlocal3
    callpropvoid {q('update')}, 2
    getlocal0
    getproperty {q('_-on')}
    getlocal3
    callpropvoid {q('update')}, 1
    getlocal0
    getproperty {q('map_')}
    getproperty {q('player_')}
    setlocal 4
    getlocal 4
    iffalse done
    getlocal0
    getproperty {q('_-on')}
    getlocal 4
    callpropvoid {q('_-Kg')}, 1
    getlocal0
    getproperty {q('map_')}
    getlocal0
    getproperty {q('_-on')}
    getlocal2
    callpropvoid {q('draw')}, 2
    getlocal0
    getproperty {q('_-Ht')}
    getlocal 4
    getproperty {q('credits_')}
    getlocal 4
    getproperty {q('_-Q7')}
    callpropvoid {q('draw')}, 2
    getlocal0
    getproperty {q('_-V1')}
    callpropvoid {q('draw')}, 0
    getlocal2
    getlocal0
    getproperty {q('spectatorFrameTime')}
    subtract
    pushshort 1000
    iflt done
    getlocal0
    getlocal2
    setproperty {q('spectatorFrameTime')}
    {status('frame')}
    done:
    getlocal0
    getlocal2
    setproperty {q('lastUpdate_')}
    returnvoid''')
    replace_method(network, '_-Lx', status('tick'), suffix=True)
    replace_method(network, '_-of', f'getlocal0\npushscope\n{status("disconnected")}\nreturnvoid')
    replace_method(network, 'onError', f'getlocal0\npushscope\n{status("error", "Native socket error")}\nreturnvoid')
    replace_method(network, '_-nc', f'''getlocal0
    pushscope
    findpropstrict {q('trace')}
    pushstring "openrotmg-spectator:error:"
    getlocal1
    getproperty {q('errorDescription_')}
    add
    callpropvoid {q('trace')}, 1
    returnvoid''')
    replace_method(root / 'com/company/assembleegameclient/game/_-07a.class.asasm', 'onAddedToStage', 'getlocal0\npushscope\nreturnvoid')

    # Only initialization and transport acknowledgements may reach the socket.
    allowed = [17, 45, 16, 22, 14, 11]
    guard = ''
    for packet in allowed:
        guard += f'getlocal1\ngetproperty {q("id_")}\npushbyte {packet}\nifeq spectatorSend\n'
    guard += 'returnvoid\nspectatorSend:'
    replace_method(connection, '_-hb', guard, prefix=True)
    replace_method(network, 'move', 'getlocal0\npushscope\nreturnvoid')

    # The watched self follows the same authoritative interpolation as remote actors.
    replace_method(network, '_-9s', f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('gs_')}
    getproperty {q('map_')}
    getproperty {q('goDict_')}
    getlocal1
    getproperty {q('objectId_')}
    getproperty MultinameL([PackageNamespace("")])
    coerce {q('GameObject', OBJECTS)}
    setlocal 4
    getlocal 4
    iffalse done
    getlocal2
    iffalse stats
    getlocal 4
    getlocal1
    getproperty {q('pos_')}
    getproperty {q('x_')}
    getlocal1
    getproperty {q('pos_')}
    getproperty {q('y_')}
    getlocal2
    getlocal3
    callpropvoid {q('_-0Iu')}, 4
    stats:
    getlocal0
    getlocal 4
    getlocal1
    getproperty {q('_-086')}
    getlocal1
    getproperty {q('objectId_')}
    getlocal0
    getproperty {net_private('_-5z')}
    equals
    callpropvoid {net_private('_-066')}, 3
    done:
    returnvoid''')
    replace_method(player, 'update', f'''getlocal0
    pushscope
    getlocal0
    getlocal1
    getlocal2
    callsuper {q('update')}, 2
    returnvalue''')
    replace_method(player, 'shoot', 'getlocal0\npushscope\nreturnvoid')
    replace_method(objects, 'damage', f'''getlocal1
    pushbyte 0
    iflt authoritative
    getlocal0
    getproperty {q('map_')}
    getproperty {q('player_')}
    getlocal0
    ifne authoritative
    returnvoid
    authoritative:''', prefix=True)


def build(tools):
    source = (ROOT / 'client.swf').read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('Spectator requires unchanged pinned 123.5.1 client.swf')
    with tempfile.TemporaryDirectory(prefix='openrotmg-spectator-') as directory:
        stage = Path(directory)
        movie = stage / 'spectator.swf'
        movie.write_bytes(source)
        def run(tool, *args):
            subprocess.run([str(tools / tool), *map(str, args)], cwd=stage, check=True)
        run('abcexport', movie)
        run('rabcdasm', stage / 'spectator-1.abc')
        root = stage / 'spectator-1'
        transform(root)
        run('rabcasm', root / 'spectator-1.main.asasm')
        run('abcreplace', movie, 1, root / 'spectator-1.main.abc')
        result = movie.read_bytes()
        if result[:3] != b'FWS' or struct.unpack_from('<I', result, 4)[0] != len(result):
            raise RuntimeError('Expected well-formed uncompressed SWF from assembler')
        result = b'CWS' + result[3:8] + zlib.compress(result[8:], 9)
        if len(result) != LOCK['outputBytes'] or hashlib.sha256(result).hexdigest() != LOCK['outputSha256']:
            raise RuntimeError('Spectator output checksum mismatch; inspect source/toolchain/transform before updating lock')
        (ROOT / 'spectator.swf').write_bytes(result)
        print(f'Spectator SHA256 {hashlib.sha256(result).hexdigest()} ({len(result)} bytes)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tools', type=Path)
    build(parser.parse_args().tools.resolve())
