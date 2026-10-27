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
    # AVM2 backward branches require an encoded label opcode, not just an assembler label.
    lines = (line.strip() for line in code.strip().splitlines() if line.strip())
    return ''.join('      ' + line + ('\n      label' if re.fullmatch(r'\w+:', line) else '') + '\n' for line in lines)


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
        returns = list(re.finditer(r'(?m)^ +returnvoid', body))
        if not returns:
            raise RuntimeError(f'Expected returnvoid in {path}:{name}')
        position = returns[-1].start()
        body = body[:position] + instructions(code) + body[position:]
    else:
        body = re.sub(r'(?ms)( {4,5}code\n).*?( {4,5}end ; code)', lambda m: m[1] + instructions(code) + m[2], body, count=1)
    # Added bootstrap/interception code can need more stack than the original method.
    body = re.sub(r'maxstack \d+', 'maxstack 24', body)
    path.write_text(text[:match.start()] + body + text[match.end():])


def add_method(path, name, params, code, locals_=2, returns=None):
    text = path.read_text()
    scope = int(re.search(r'initscopedepth (\d+)', text)[1])
    body = f'''  trait method {q(name)}
   method
    refid "spectator/{path.stem}/{name}"
{''.join('    param ' + p + chr(10) for p in params)}    returns {returns or q('void')}
    body
     maxstack 24
     localcount {locals_}
     initscopedepth {scope}
     maxscopedepth {scope + 1}
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
    setproperty {q('spectatorGame')}
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
    getlocal0
    getproperty {q('spectatorGame')}
    iffalse blocked
    getlocal0
    getproperty {q('spectatorGame')}
    getlocal1
    callpropvoid {q('spectatorInput')}, 1
    blocked:
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
    getlocal0
    getlocal 4
    callpropvoid {q('spectatorBind')}, 1
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
    findpropstrict {q('trace')}
    pushstring "openrotmg-spectator:source:"
    getlocal0
    getproperty {q('spectatorSource')}
    add
    callpropvoid {q('trace')}, 1
    done:
    getlocal0
    getlocal2
    setproperty {q('lastUpdate_')}
    returnvoid''')
    replace_method(network, '_-02H', status('tick'), suffix=True)
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
    spectator_interactions(root)
    from spectator_cursor import transform as cursor_transform
    cursor_transform(root)

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


def spectator_interactions(root):
    ui = 'com.company.assembleegameclient.ui'
    player_type = q('Player', OBJECTS)
    mouse = q('MouseEvent', 'flash.events')
    index = 'MultinameL([PackageNamespace("")])'
    game = root / 'com/company/assembleegameclient/game/GameSprite.class.asasm'
    minimap = root / 'com/company/assembleegameclient/ui/_-ej.class.asasm'
    chat = root / 'com/company/assembleegameclient/ui/_-4D.class.asasm'

    def slot(path, name, type_, value):
        text = path.read_text()
        path.write_text(text.replace(' end ; instance',
            f'  trait slot {q(name)} type {type_} value {value} end\n end ; instance'))

    def splice(path, anchor, code, replace=False):
        text = path.read_text()
        if text.count(anchor) != 1:
            raise RuntimeError(f'Expected one interaction anchor in {path}: {anchor}')
        path.write_text(text.replace(anchor, ('' if replace else anchor + '\n') + instructions(code)))

    slot(root / 'WebMain.class.asasm', 'spectatorGame', q('GameSprite', GAME), 'Null()')
    slot(game, 'spectatorSource', q('int'), 'Integer(-1)')
    add_method(game, 'spectatorBind', [player_type], f'''getlocal0
    pushscope
    pushbyte -1
    setlocal2
    getlocal1
    iffalse compare
    getlocal1
    getproperty {q('objectId_')}
    setlocal2
    compare:
    getlocal2
    getlocal0
    getproperty {q('spectatorSource')}
    ifeq done
    getlocal0
    getlocal2
    setproperty {q('spectatorSource')}
    findpropstrict {q('trace')}
    pushstring "openrotmg-spectator:source:"
    getlocal2
    add
    callpropvoid {q('trace')}, 1
    done:
    returnvoid''', locals_=3)
    add_method(game, 'spectatorInspect', [player_type, mouse], f'''getlocal0
    pushscope
    getlocal1
    iffalse done
    getlocal0
    getproperty {q('map_')}
    setlocal3
    getlocal3
    getproperty {q('player_')}
    iffalse done
    getlocal1
    getproperty {q('map_')}
    getlocal3
    ifne done
    getlocal3
    getproperty {q('goDict_')}
    getlocal1
    getproperty {q('objectId_')}
    getproperty {index}
    getlocal1
    ifne done
    getlocal0
    getlocal3
    getproperty {q('player_')}
    callpropvoid {q('spectatorBind')}, 1
    findpropstrict {q('trace')}
    pushstring "openrotmg-spectator:inspect:"
    getlocal0
    getproperty {q('spectatorSource')}
    add
    pushstring ":"
    add
    getlocal1
    getproperty {q('objectId_')}
    add
    pushstring ":"
    add
    getlocal2
    getproperty {q('stageX')}
    add
    pushstring ":"
    add
    getlocal2
    getproperty {q('stageY')}
    add
    callpropvoid {q('trace')}, 1
    done:
    returnvoid''', locals_=4)

    # Match _-w6.onMouseDown inspection for both buttons without restoring its playable menu.
    add_method(game, 'spectatorInput', [q('Event', 'flash.events')], f'''getlocal0
    pushscope
    getlocal1
    astype {mouse}
    setlocal2
    getlocal2
    iffalse done
    getlocal2
    getproperty {q('type')}
    setlocal 5
    getlocal 5
    pushstring "rightMouseDown"
    ifne inputType
    pushstring "mouseDown"
    setlocal 5
    inputType:
    getlocal0
    getproperty {q('map_')}
    getproperty {q('player_')}
    iffalse done
    getlocal 5
    pushstring "mouseDown"
    ifne targets
    getlocal0
    getproperty {q('textBox_')}
    getlocal2
    callproperty {q('spectatorPlayer')}, 1
    setlocal 4
    getlocal 4
    iffalse targets
    getlocal0
    getlocal 4
    getlocal2
    callpropvoid {q('spectatorInspect')}, 2
    returnvoid
    targets:
    getlocal2
    getproperty {q('target')}
    astype {q('DisplayObject', 'flash.display')}
    setlocal3
    ancestors:
    getlocal3
    iffalse world
    getlocal3
    istype {q('_-ej', ui)}
    iffalse nearby
    getlocal3
    getlocal2
    callpropvoid {q('spectatorInput')}, 1
    returnvoid
    nearby:
    getlocal 5
    pushstring "mouseDown"
    ifne next
    getlocal3
    istype {q('_-gV', ui)}
    iffalse next
    getlocal3
    getproperty {q('parent')}
    istype {q('_-w6', '_-Rv')}
    iftrue inspectRow
    getlocal3
    getproperty {q('parent')}
    istype {q('_-06M', '_-0DB')}
    iffalse next
    getlocal3
    getproperty {q('parent')}
    setlocal 4
    getlocal 4
    getproperty {q('parent')}
    getlocal 4
    callpropvoid {q('removeChild')}, 1
    inspectRow:
    getlocal0
    getlocal3
    getproperty {q('go_')}
    astype {player_type}
    getlocal2
    callpropvoid {q('spectatorInspect')}, 2
    returnvoid
    next:
    getlocal3
    getproperty {q('parent')}
    setlocal3
    jump ancestors
    world:
    getlocal 5
    pushstring "mouseDown"
    ifne done
    getlocal0
    getproperty {q('map_')}
    getlocal2
    getproperty {q('target')}
    astype {q('DisplayObject', 'flash.display')}
    callproperty {q('contains')}, 1
    iffalse done
    getlocal0
    getlocal0
    getproperty {q('map_')}
    callproperty {q('spectatorPlayer')}, 0
    getlocal2
    callpropvoid {q('spectatorInspect')}, 2
    done:
    returnvoid''', locals_=6)

    # The rendered quad and draw order are authoritative, not inferred world-distance circles.
    world = root / 'com/company/assembleegameclient/map/_-Xl.class.asasm'
    code = f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('_-u2')}
    getproperty {q('length')}
    setlocal1
    loop:
    declocal_i 1
    getlocal1
    pushbyte 0
    iflt missing
    getlocal0
    getproperty {q('_-u2')}
    getlocal1
    getproperty {index}
    astype {q('GameObject', OBJECTS)}
    setlocal2
    getlocal2
    iffalse loop
    getlocal2
    getproperty {q('_-1D')}
    iffalse loop
    getlocal2
    getlocal0
    getproperty {q('mouseX')}
    getlocal0
    getproperty {q('mouseY')}
    callproperty {q('spectatorHit')}, 2
    iffalse loop
    getlocal2
    astype {player_type}
    returnvalue
    missing:
    pushnull
    returnvalue'''
    add_method(world, 'spectatorPlayer', [], code, locals_=3, returns=player_type)
    vertices = 'QName(ProtectedNamespace("_-iP"), "vS_")'
    code = f'''getlocal0
    pushscope
    getlocal0
    getproperty {vertices}
    setlocal3
    getlocal3
    getproperty {q('length')}
    pushbyte 8
    ifne missing
    '''
    for local, vertex, branch in [(1, 0, 'iflt'), (1, 2, 'ifgt'), (2, 1, 'iflt'), (2, 5, 'ifgt')]:
        code += f'getlocal {local}\ngetlocal3\npushbyte {vertex}\ngetproperty {index}\n{branch} missing\n'
    code += f'''getlocal0
    getproperty QName(ProtectedNamespace("_-iP"), "bitmapFill_")
    setlocal3
    getlocal3
    iffalse missing
    getlocal3
    getproperty {q('bitmapData')}
    iffalse missing
    getlocal3
    getproperty {q('matrix')}
    callproperty {q('clone')}, 0
    setlocal 4
    getlocal 4
    callpropvoid {q('invert')}, 0
    getlocal 4
    findpropstrict {q('Point', 'flash.geom')}
    getlocal1
    getlocal2
    constructprop {q('Point', 'flash.geom')}, 2
    callproperty {q('transformPoint')}, 1
    setlocal 5
    getlocal3
    getproperty {q('bitmapData')}
    getlocal 5
    getproperty {q('x')}
    getlocal 5
    getproperty {q('y')}
    callproperty {q('getPixel32')}, 2
    pushbyte 24
    urshift
    pushbyte 0
    greaterthan
    returnvalue
    missing:
    pushfalse
    returnvalue'''
    add_method(root / 'com/company/assembleegameclient/objects/GameObject.class.asasm',
               'spectatorHit', [q('Number'), q('Number')], code, locals_=6, returns=q('Boolean'))

    # Never construct bag, shop or account panels: restore only the native nearby-player list.
    replace_method(root / '_-Rv/_-QV.class.asasm', 'draw', f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('_-VD')}
    getproperty {q('parent')}
    iftrue draw
    getlocal0
    getlocal0
    getproperty {q('_-VD')}
    callpropvoid {q('addChild')}, 1
    draw:
    getlocal0
    getlocal0
    getproperty {q('_-VD')}
    setproperty {q('_-G2')}
    getlocal0
    getproperty {q('_-VD')}
    callpropvoid {q('draw')}, 0
    returnvoid''')

    mini_private = lambda name: private(name, ui + ':_-ej#0')
    add_method(minimap, 'spectatorInput', [mouse], f'''getlocal0
    pushscope
    getlocal1
    getproperty {q('type')}
    pushstring "mouseWheel"
    ifne click
    getlocal1
    getproperty {q('delta')}
    pushbyte 0
    ifgt zoomIn
    jump zoomOut
    click:
    getlocal1
    getproperty {q('type')}
    pushstring "click"
    ifne done
    getlocal0
    getproperty {q('_-tk')}
    getlocal1
    getproperty {q('target')}
    callproperty {q('contains')}, 1
    iftrue zoomOut
    getlocal0
    getproperty {q('_-1-')}
    getlocal1
    getproperty {q('target')}
    callproperty {q('contains')}, 1
    iftrue zoomIn
    getlocal0
    callpropvoid {q('draw')}, 0
    getlocal0
    getproperty {mini_private('_-nC')}
    getproperty {q('length')}
    pushbyte 1
    ifne candidates
    getlocal0
    getproperty {q('map_')}
    getproperty {q('gs_')}
    getlocal0
    getproperty {mini_private('_-nC')}
    pushbyte 0
    getproperty {index}
    getlocal1
    callpropvoid {q('spectatorInspect')}, 2
    returnvoid
    candidates:
    getlocal0
    getlocal1
    callpropvoid {mini_private('_-RB')}, 1
    returnvoid
    zoomIn:
    getlocal0
    callpropvoid {q('_-Kr')}, 0
    returnvoid
    zoomOut:
    getlocal0
    callpropvoid {q('_-w-')}, 0
    done:
    returnvoid''')

    # These menus may still be reached by native hover components; strip every account/action entry.
    replace_method(root / '_-0DB/_-02p.class.asasm', '', f'''getlocal0
    pushscope
    getlocal0
    pushint 3552822
    pushint 16777215
    constructsuper 2
    getlocal0
    getlocal1
    setproperty {q('gs_')}
    getlocal0
    getlocal2
    setproperty {q('player_')}
    getlocal0
    findpropstrict {q('_-gV', ui)}
    pushint 11776947
    pushtrue
    getlocal2
    constructprop {q('_-gV', ui)}, 3
    callpropvoid {q('addChild')}, 1
    returnvoid''', constructor=True)
    replace_method(root / '_-0DB/_-06M.class.asasm', '', f'''getlocal0
    pushscope
    getlocal0
    pushint 3552822
    pushint 16777215
    constructsuper 2
    getlocal0
    getlocal1
    setproperty {q('map_')}
    getlocal0
    getlocal2
    setproperty {q('_-nC')}
    pushbyte 0
    setlocal3
    loop:
    getlocal3
    getlocal2
    getproperty {q('length')}
    ifge done
    findpropstrict {q('_-gV', ui)}
    pushint 11776947
    pushtrue
    getlocal2
    getlocal3
    getproperty {index}
    constructprop {q('_-gV', ui)}, 3
    setlocal 4
    getlocal 4
    getlocal3
    pushbyte 32
    multiply
    pushbyte 4
    add
    setproperty {q('y')}
    getlocal0
    getlocal 4
    callpropvoid {q('addChild')}, 1
    inclocal_i 3
    jump loop
    done:
    returnvoid''', constructor=True)

    # Keep packet actor references on public chat; names and classes never classify bots.
    slot(root / 'com/company/assembleegameclient/ui/_-0At.class.asasm', 'spectatorActor', player_type, 'Null()')
    anchor = f'      constructprop       {q("_-0At", ui)}, 7\n      coerce              {q("_-0At", ui)}\n      setlocal            8'
    splice(chat, anchor, f'''getlocal 8
    getlocal0
    getproperty {private('gs_', ui + ':_-4D#0')}
    getproperty {q('map_')}
    getproperty {q('goDict_')}
    getlocal2
    getproperty {index}
    astype {player_type}
    setproperty {q('spectatorActor')}''')
    anchor = f'      callproperty        {q("_-0Hu")}, 0\n      coerce              {q("TextBlock", "flash.text.engine")}\n      setlocal            6'
    splice(chat, anchor, f'''getlocal 6
    getlocal 5
    setproperty {q('userData')}''')
    replace_method(chat, '', f'''getlex {private('_-dL', ui + ':_-4D#0')}
    pushbyte 0
    setproperty {q('length')}
    getlocal0
    callpropvoid {private('_-x5', ui + ':_-4D#0')}, 0''', suffix=True, constructor=True)
    # Ruffle has no FTE atom picking. Measure the very same native name/font, not a guessed DOM hitbox.
    message = root / 'com/company/assembleegameclient/ui/_-0At.class.asasm'
    slot(message, 'spectatorNameWidth', q('Number'), 'Integer(0)')
    anchor = f'      findpropstrict      {q("TextElement", "flash.text.engine")}\n      pushstring          "<"'
    splice(message, anchor, 'getlocal0\npushstring "<"', replace=True)
    anchor = f'      getlocal2\n      constructprop       {q("TextElement", "flash.text.engine")}, 2'
    splice(message, anchor, f'getlocal2\ncallproperty {q("spectatorName")}, 2', replace=True)
    add_method(message, 'spectatorName', [q('String'), q('ElementFormat', 'flash.text.engine')], f'''getlocal0
    pushscope
    findpropstrict {q('TextBlock', 'flash.text.engine')}
    findpropstrict {q('TextElement', 'flash.text.engine')}
    getlocal1
    getlocal2
    constructprop {q('TextElement', 'flash.text.engine')}, 2
    constructprop {q('TextBlock', 'flash.text.engine')}, 1
    pushnull
    pushshort 800
    callproperty {q('createTextLine')}, 2
    setlocal3
    getlocal0
    getlocal3
    getproperty {q('textWidth')}
    setproperty {q('spectatorNameWidth')}
    findpropstrict {q('TextElement', 'flash.text.engine')}
    getlocal1
    getlocal2
    constructprop {q('TextElement', 'flash.text.engine')}, 2
    returnvalue''', locals_=4, returns=q('TextElement', 'flash.text.engine'))
    add_method(chat, 'spectatorPlayer', [mouse], f'''getlocal0
    pushscope
    pushbyte -1
    setlocal2
    loop:
    inclocal_i 2
    getlocal2
    getlocal0
    getproperty {q('_-01P')}
    getproperty {q('numChildren')}
    ifge missing
    getlocal0
    getproperty {q('_-01P')}
    getlocal2
    callproperty {q('getChildAt')}, 1
    setlocal 7
    getlocal 7
    getproperty {q('numChildren')}
    iffalse loop
    getlocal 7
    pushbyte 0
    callproperty {q('getChildAt')}, 1
    astype {q('TextLine', 'flash.text.engine')}
    setlocal3
    getlocal3
    iffalse loop
    getlocal3
    getproperty {q('textBlock')}
    getproperty {q('userData')}
    astype {q('_-0At', ui)}
    setlocal 4
    getlocal 4
    iffalse loop
    getlocal 4
    getproperty {q('recipient_')}
    pushstring ""
    ifne loop
    getlocal 4
    getproperty {q('spectatorNameWidth')}
    pushbyte 0
    ifle loop
    getlocal3
    findpropstrict {q('Point', 'flash.geom')}
    getlocal1
    getproperty {q('stageX')}
    getlocal1
    getproperty {q('stageY')}
    constructprop {q('Point', 'flash.geom')}, 2
    callproperty {q('globalToLocal')}, 1
    setlocal 5
    getlocal 5
    getproperty {q('y')}
    getlocal3
    getproperty {q('ascent')}
    negate
    iflt loop
    getlocal 5
    getproperty {q('y')}
    getlocal3
    getproperty {q('descent')}
    ifgt loop
    pushbyte 0
    setlocal 6
    getlocal 4
    getproperty {q('_-LP')}
    iffalse name
    getlocal 4
    getproperty {q('_-LP')}
    getproperty {q('width')}
    pushbyte 2
    add
    setlocal 6
    name:
    getlocal 5
    getproperty {q('x')}
    getlocal 6
    iflt loop
    getlocal 5
    getproperty {q('x')}
    getlocal 6
    getlocal 4
    getproperty {q('spectatorNameWidth')}
    add
    ifgt loop
    getlocal 4
    getproperty {q('spectatorActor')}
    returnvalue
    missing:
    pushnull
    returnvalue''', locals_=8, returns=player_type)


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
            raise RuntimeError(f'Spectator output checksum mismatch: SHA256 {hashlib.sha256(result).hexdigest()} ({len(result)} bytes); inspect source/toolchain/transform before updating lock')
        (ROOT / 'spectator.swf').write_bytes(result)
        print(f'Spectator SHA256 {hashlib.sha256(result).hexdigest()} ({len(result)} bytes)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tools', type=Path)
    build(parser.parse_args().tools.resolve())
