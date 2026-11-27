"""Derive the Easy Client from a server-patched 123.5.1 movie.

Usage: python3 scripts/build_easy.py /path/to/RABCDAsm INPUT.swf OUTPUT.swf
Disassembles the game ABC, applies the Easy Client method edits and writes an uncompressed movie.
"""
import argparse
import re
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

from build_spectator import q, private, instructions, add_method, OBJECTS, PARAMETERS

UI = 'com.company.assembleegameclient.ui'
INDEX = 'MultinameL([PackageNamespace("")])'
PLATFORM = 'openrotmg-easy'
DATA = f'getlex {q("Parameters", PARAMETERS)}\ngetproperty {q("data_")}'


def edit(path, method, old, new):
    text = path.read_text()
    if text.count(method) != 1:
        raise RuntimeError(f'Expected one {method} in {path.name}')
    start = text.index(method)
    indent = re.match(r' *', text[text.rfind('\n', 0, start) + 1:]).group()
    end = text.index('\n' + indent + 'end ; ', start)
    body = text[start:end]
    if body.count(old) != 1:
        raise RuntimeError(f'Expected one Easy Client anchor in {path.name} {method}: {old!r}')
    # Inserted code can need more operand stack than the original method.
    body = re.sub(r'maxstack (\d+)', lambda m: f'maxstack {max(int(m[1]), 24)}', body.replace(old, new), count=1)
    path.write_text(text[:start] + body + text[end:])


def prefix(path, method, code):
    text = path.read_text()
    start = text.index(method)
    code_line = re.compile(r'(?m)^ +code\n').search(text, start)
    stack = re.compile(r'maxstack \d+').search(text, start)
    text = text[:code_line.end()] + instructions(code) + text[code_line.end():]
    path.write_text(text[:stack.start()] + f'maxstack {max(int(stack[0].split()[1]), 24)}' + text[stack.end():])


def method(name, ns=q):
    return f'trait method {ns(name)}'


def static_slot(path, name, type_, slot):
    text = path.read_text()
    if text.count('\nend ; class') != 1:
        raise RuntimeError(f'Expected one class in {path}')
    path.write_text(text.replace('\nend ; class', f'\n trait slot {q(name)} slotid {slot} type {type_} end\nend ; class'))


def slot(path, name, type_, value):
    text = path.read_text()
    path.write_text(text.replace(' end ; instance', f'  trait slot {q(name)} type {type_} value {value} end\n end ; instance', 1))


def choice(name, title, description, labels, values):
    code = f'''getlocal0
    findpropstrict {q('_-0Ij', '_-0CP')}
    pushstring "{name}"
    getlex {q('Vector', '__AS3__.vec')}
    getlex {q('String')}
    applytype 1
    pushbyte {len(labels)}
    construct 1\n'''
    for index, label in enumerate(labels):
        code += f'dup\npushbyte {index}\npushstring "{label}"\nsetproperty {INDEX}\n'
    code += ''.join(values) + f'''newarray {len(values)}
    pushstring "{title}"
    pushstring "{description}"
    pushnull
    constructprop {q('_-0Ij', '_-0CP')}, 6
    callpropvoid {private('_-yZ', '_-0CP:Options#0')}, 1\n'''
    return code


def transform(root):
    parameters = root / 'com/company/assembleegameclient/parameters/Parameters.class.asasm'
    camera = root / 'com/company/assembleegameclient/map/_-0Dv.class.asasm'
    world = root / 'com/company/assembleegameclient/map/_-Xl.class.asasm'
    objects = root / 'com/company/assembleegameclient/objects/GameObject.class.asasm'
    player = root / 'com/company/assembleegameclient/objects/Player.class.asasm'
    network = root / 'com/company/assembleegameclient/net/_-1f.class.asasm'
    game = root / 'com/company/assembleegameclient/game/GameSprite.class.asasm'
    chat = root / 'com/company/assembleegameclient/ui/_-4D.class.asasm'
    minimap = root / 'com/company/assembleegameclient/ui/_-ej.class.asasm'
    options = root / '_-0CP/Options.class.asasm'
    player_type = q('Player', OBJECTS)
    mouse = q('MouseEvent', 'flash.events')
    key = lambda name: f'getlex              {q("_-HV", "com.company.util")}\n     getproperty         {q(name)}'

    # A separate options store keeps Easy defaults from rewriting Classic players' saved settings.
    edit(parameters, method('load'), '"AssembleeGameClientOptions"', '"OpenRotMGEasyClientOptions"')
    defaults = method('_-fX')
    for name, old, new in [('escapeToNexus', '_-SS', 'R'), ('escapeToNexus2', 'F5', '_-SS'), ('resetToDefaultCameraAngle', 'R', 'Z')]:
        edit(parameters, defaults, f'pushstring          "{name}"\n     {key(old)}', f'pushstring          "{name}"\n     {key(new)}')
    edit(parameters, defaults, 'pushstring          "allowRotation"\n     pushfalse', 'pushstring          "allowRotation"\n     pushtrue')
    for name in ['cameraAngle', 'defaultCameraAngle']:
        edit(parameters, defaults, f'pushstring          "{name}"\n     pushbyte            7', f'pushstring          "{name}"\n     pushbyte            0')
    default = lambda name, value: f'getlocal0\npushstring "{name}"\n{value}\ncallpropvoid {private("_-iw", PARAMETERS + ":Parameters/class#0")}, 2\n'
    prefix(parameters, defaults, default('easyZoom', 'pushshort 150') + default('easyOthers', 'pushbyte 100')
           + default('easyAllyShots', 'pushtrue'))
    edit(parameters, ' cinit\n', '"[/tutorial]: enter the tutorial\\n"',
         '"[/tutorial]: enter the tutorial\\n[/vault]: go to your vault\\n[/realm]: go to the most populated realm\\n"')

    # Only the gameplay camera zooms; title and other scenes keep their own cameras at 1.
    slot(camera, 'easyZoom', q('Number'), 'Integer(1)')
    scaled = ''.join(f'getlocal2\ngetproperty {q(side)}\ngetlocal0\ngetproperty {q("easyZoom")}\nmultiply\n' for side in ['x', 'y', 'width', 'height'])
    edit(camera, method('_-Kg'), '      getlocal2\n      pushfalse\n      callpropvoid        QName(PackageNamespace(""), "_-K"), 6',
         instructions(f'''getlocal0
         {DATA}
         getproperty {q('easyZoom')}
         pushbyte 100
         divide
         setproperty {q('easyZoom')}
         findpropstrict {q('Rectangle', 'flash.geom')}
         {scaled}
         constructprop {q('Rectangle', 'flash.geom')}, 4
         pushfalse''') + '      callpropvoid        QName(PackageNamespace(""), "_-K"), 6')
    zoom = f'getlocal1\ngetproperty {q("easyZoom")}'
    for axis in ['x', 'y']:
        edit(world, method('draw'), f'getproperty         {q(axis)}\n      negate\n      initproperty        {q(axis)}',
             f'getproperty         {q(axis)}\n      negate\n' + instructions(f'{zoom}\ndivide') + f'      initproperty        {q(axis)}')
    edit(world, method('draw'), f'initproperty        {q("y")}\n', f'initproperty        {q("y")}\n' + instructions(
        ''.join(f'getlocal0\npushbyte 1\n{zoom}\ndivide\nsetproperty {q(scale)}\n' for scale in ['scaleX', 'scaleY'])))

    # Ally shots are presentation only: the server never consults their client-side hits.
    edit(network, method('_-PF', lambda n: private(n, 'com.company.assembleegameclient.net:_-1f#0')),
         f'callpropvoid        {q("addObj")}, 3', f'callpropvoid        {q("easyAllyShot")}, 3')
    add_method(world, 'easyAllyShot', [q('BasicObject', OBJECTS), q('Number'), q('Number')], f'''getlocal0
    pushscope
    {DATA}
    getproperty {q('easyAllyShots')}
    iffalse done
    getlocal0
    getlocal1
    getlocal2
    getlocal3
    callpropvoid {q('addObj')}, 3
    done:
    returnvoid''', locals_=4)

    # Every object shares one Graphics, so per-player opacity uses faded copies of its textures.
    static_slot(objects, 'easyFades', q('Dictionary', 'flash.utils'), 100)
    static_slot(objects, 'easyFadeAlpha', q('Number'), 101)
    add_method(objects, 'easyAlpha', [], f'''getlocal0
    pushscope
    getlocal0
    istype {player_type}
    iffalse opaque
    getlocal0
    getproperty {q('map_')}
    getproperty {q('player_')}
    getlocal0
    ifstricteq opaque
    {DATA}
    getproperty {q('easyOthers')}
    pushbyte 100
    divide
    returnvalue
    opaque:
    pushbyte 1
    returnvalue''', returns=q('Number'))
    fades = f'getlex {q("GameObject", OBJECTS)}\ngetproperty {q("easyFades")}'
    add_method(objects, 'easyFade', [q('BitmapData', 'flash.display')], f'''getlocal0
    pushscope
    getlocal0
    callproperty {q('easyAlpha')}, 0
    setlocal2
    getlocal2
    pushbyte 1
    ifge keep
    getlocal1
    iffalse keep
    getlex {q('GameObject', OBJECTS)}
    getproperty {q('easyFadeAlpha')}
    getlocal2
    ifeq cached
    getlex {q('GameObject', OBJECTS)}
    findpropstrict {q('Dictionary', 'flash.utils')}
    pushtrue
    constructprop {q('Dictionary', 'flash.utils')}, 1
    setproperty {q('easyFades')}
    getlex {q('GameObject', OBJECTS)}
    getlocal2
    setproperty {q('easyFadeAlpha')}
    cached:
    {fades}
    getlocal1
    getproperty {INDEX}
    coerce {q('BitmapData', 'flash.display')}
    setlocal3
    getlocal3
    iftrue done
    getlocal1
    callproperty {q('clone')}, 0
    coerce {q('BitmapData', 'flash.display')}
    setlocal3
    getlocal3
    getlocal3
    getproperty {q('rect')}
    findpropstrict {q('ColorTransform', 'flash.geom')}
    pushbyte 1
    pushbyte 1
    pushbyte 1
    getlocal2
    constructprop {q('ColorTransform', 'flash.geom')}, 4
    callpropvoid {q('colorTransform')}, 2
    {fades}
    getlocal1
    getlocal3
    setproperty {INDEX}
    done:
    getlocal3
    returnvalue
    keep:
    getlocal1
    returnvalue''', locals_=4, returns=q('BitmapData', 'flash.display'))
    texture = f'callproperty        QName(ProtectedNamespace("_-iP"), "getTexture"), 2\n      coerce              {q("BitmapData", "flash.display")}\n      setlocal            4\n'
    edit(objects, method('draw'), texture, texture + instructions(f'getlocal0\ngetlocal 4\ncallproperty {q("easyFade")}, 1\ncoerce {q("BitmapData", "flash.display")}\nsetlocal 4'))
    name = f'getproperty         {q("_-Ug")}\n      setproperty         {q("bitmapData")}'
    edit(objects, method('_-oL'), name, f'getproperty         {q("_-Ug")}\n' + instructions(f'getlocal0\nswap\ncallproperty {q("easyFade")}, 1') + f'      setproperty         {q("bitmapData")}')
    hidden = f'getlocal0\ncallproperty {q("easyAlpha")}, 0\npushbyte 0\nifgt visible\nreturnvoid\nvisible:'
    prefix(player, method('draw'), hidden)
    prefix(objects, method('drawShadow'), hidden)

    # Right-click teleports through the ordinary Player.teleportTo cooldown and Teleport packet.
    edit(chat, method('_-x5', lambda n: private(n, UI + ':_-4D#0')),
         f'callproperty        {q("_-0Hu")}, 0\n      coerce              {q("TextBlock", "flash.text.engine")}\n      setlocal            6\n',
         f'callproperty        {q("_-0Hu")}, 0\n      coerce              {q("TextBlock", "flash.text.engine")}\n      setlocal            6\n'
         + instructions(f'getlocal 6\ngetlocal 5\nsetproperty {q("userData")}'))
    add_method(chat, 'easyTarget', [mouse], f'''getlocal0
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
    coerce {q('DisplayObjectContainer', 'flash.display')}
    setlocal3
    getlocal3
    getproperty {q('visible')}
    iffalse loop
    getlocal3
    getlocal1
    getproperty {q('stageX')}
    getlocal1
    getproperty {q('stageY')}
    callproperty {q('hitTestPoint')}, 2
    iffalse loop
    getlocal3
    pushbyte 0
    callproperty {q('getChildAt')}, 1
    astype {q('TextLine', 'flash.text.engine')}
    setlocal 4
    getlocal 4
    iffalse loop
    getlocal 4
    getproperty {q('textBlock')}
    getproperty {q('userData')}
    astype {q('_-0At', UI)}
    setlocal 4
    getlocal 4
    iffalse loop
    getlocal 4
    getproperty {q('name_')}
    returnvalue
    missing:
    pushnull
    returnvalue''', locals_=5, returns=q('String'))
    add_method(world, 'easyPlayer', [q('String')], f'''getlocal0
    pushscope
    pushbyte 0
    setlocal2
    getlocal0
    getproperty {q('goDict_')}
    coerce_a
    setlocal3
    loop:
    hasnext2 3, 2
    iffalse missing
    getlocal3
    getlocal2
    nextvalue
    astype {player_type}
    setlocal 4
    getlocal 4
    iffalse loop
    getlocal 4
    getproperty {q('name_')}
    getlocal1
    ifne loop
    getlocal 4
    returnvalue
    missing:
    pushnull
    returnvalue''', locals_=5, returns=player_type)
    add_method(minimap, 'easyTarget', [], f'''getlocal0
    pushscope
    getlocal0
    callpropvoid {q('draw')}, 0
    getlocal0
    getproperty {private('_-nC', UI + ':_-ej#0')}
    getproperty {q('length')}
    pushbyte 0
    ifeq missing
    getlocal0
    getproperty {private('_-nC', UI + ':_-ej#0')}
    pushbyte 0
    getproperty {INDEX}
    returnvalue
    missing:
    pushnull
    returnvalue''', locals_=1, returns=player_type)
    error = lambda text: f'''getlocal0
    getproperty {q('textBox_')}
    getlex {q('Parameters', PARAMETERS)}
    getproperty {q('_-kX')}
    {text}
    callpropvoid {q('addText')}, 2
    returnvoid'''
    add_method(game, 'easyRightClick', [mouse], f'''getlocal0
    pushscope
    getlocal0
    getproperty {q('map_')}
    getproperty {q('player_')}
    coerce {player_type}
    setlocal2
    getlocal2
    iffalse done
    getlocal0
    getproperty {q('textBox_')}
    getlocal1
    callproperty {q('easyTarget')}, 1
    coerce_s
    setlocal3
    getlocal3
    iffalse minimap
    getlocal0
    getproperty {q('map_')}
    getlocal3
    callproperty {q('easyPlayer')}, 1
    coerce {player_type}
    setlocal 4
    getlocal 4
    iftrue teleport
    {error('pushstring "Can not teleport to "' + chr(10) + 'getlocal3' + chr(10) + 'add' + chr(10) + 'pushstring ": not in this area."' + chr(10) + 'add')}
    minimap:
    getlocal1
    getproperty {q('target')}
    astype {q('DisplayObject', 'flash.display')}
    setlocal 5
    ancestors:
    getlocal 5
    iffalse done
    getlocal 5
    istype {q('_-ej', UI)}
    iftrue found
    getlocal 5
    getproperty {q('parent')}
    setlocal 5
    jump ancestors
    found:
    getlocal 5
    astype {q('_-ej', UI)}
    callproperty {q('easyTarget')}, 0
    coerce {player_type}
    setlocal 4
    getlocal 4
    iffalse done
    teleport:
    getlocal0
    getproperty {q('map_')}
    getproperty {q('allowPlayerTeleport_')}
    iftrue allowed
    {error('pushstring "You can not teleport here."')}
    allowed:
    getlocal2
    getlocal 4
    callpropvoid {q('teleportTo')}, 1
    done:
    returnvoid''', locals_=6)
    listen = lambda verb: f'getlocal0\ngetproperty {q("stage")}\npushstring "rightMouseDown"\ngetlocal0\ngetproperty {q("easyRightClick")}\ncallpropvoid {q(verb)}, 2'
    prefix(game, method('onAddedToStage'), listen('addEventListener'))
    prefix(game, method('onRemovedFromStage'), listen('removeEventListener'))

    # The server enables Easy-only chat shortcuts from this self-declared Hello platform.
    send = f'getproperty         {q("_-08")}\n      getlocal2\n      callpropvoid        {q("_-hb")}, 1'
    edit(network, method('_-ux', lambda n: private(n, 'com.company.assembleegameclient.net:_-1f#0')), send,
         instructions(f'getlocal2\npushstring "{PLATFORM}"\nsetproperty {q("playPlatform")}') + '      ' + send)

    prefix(options, method('_-RE', lambda n: private(n, '_-0CP:Options#0')), choice('easyZoom', 'Zoom Out', 'How far the camera is zoomed out',
                                           ['100%', '150%', '200%', '250%', '300%'], [f'pushshort {v}\n' for v in [100, 150, 200, 250, 300]])
                   + choice('easyOthers', 'Other Players', 'Opacity of other players and their names',
                            ['100%', '75%', '50%', '25%', '10%', '0%'], [f'pushbyte {v}\n' for v in [100, 75, 50, 25, 10, 0]])
                   + choice('easyAllyShots', 'Ally Projectiles', 'Show projectiles fired by other players',
                            ['On', 'Off'], ['pushtrue\n', 'pushfalse\n']))


def tags(movie):
    position = 8 + ((5 + 4 * (movie[8] >> 3) + 7) // 8) + 4
    result = [(None, movie[8:position], b'')]
    while position < len(movie):
        header, = struct.unpack_from('<H', movie, position)
        length, size = header & 63, 2
        if length == 63:
            length, = struct.unpack_from('<I', movie, position + 2)
            size = 6
        result.append((header >> 6, movie[position:position + size], movie[position + size:position + size + length]))
        position += size + length
    return result


def build(tools, source):
    if source[:3] == b'CWS':
        source = b'FWS' + source[3:8] + zlib.decompress(source[8:])
    if source[:3] != b'FWS' or struct.unpack_from('<I', source, 4)[0] != len(source):
        raise RuntimeError('Easy Client requires a well-formed 123.5.1 movie')
    parts = tags(source)
    abcs = [index for index, part in enumerate(parts) if part[0] == 82]
    if len(abcs) != 2:
        raise RuntimeError(f'Expected two DoABC tags, found {len(abcs)}')
    tag, _, data = parts[abcs[1]]
    header = data[:data.index(0, 4) + 1]
    with tempfile.TemporaryDirectory(prefix='openrotmg-easy-') as directory:
        stage = Path(directory)
        (stage / 'game.abc').write_bytes(data[len(header):])
        subprocess.run([str(tools / 'rabcdasm'), str(stage / 'game.abc')], check=True)
        transform(stage / 'game')
        subprocess.run([str(tools / 'rabcasm'), str(stage / 'game/game.main.asasm')], check=True)
        data = header + (stage / 'game/game.main.abc').read_bytes()
        parts[abcs[1]] = (tag, struct.pack('<HI', tag << 6 | 63, len(data)), data)
    body = b''.join(head + data for _, head, data in parts)
    return b'FWS' + source[3:4] + struct.pack('<I', len(body) + 8) + body


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tools', type=Path)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    movie = build(args.tools.resolve(), args.input.read_bytes())
    args.output.write_bytes(movie)
    print(f'Easy Client {args.output} ({len(movie)} bytes)')
