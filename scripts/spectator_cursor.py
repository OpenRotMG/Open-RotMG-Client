"""Spectator-only packet 250 and native camera-projected, read-only marker."""
from build_spectator import GAME, NET, add_method, instructions, q, replace_method, status


def transform(root):
    game = root / 'com/company/assembleegameclient/game/GameSprite.class.asasm'
    network = root / 'com/company/assembleegameclient/net/_-1f.class.asasm'
    packet = root / 'com/company/net/_-098.class.asasm'

    def slot(path, name, type_, value):
        text = path.read_text()
        path.write_text(text.replace(' end ; instance',
            f'  trait slot {q(name)} type {q(type_)} value {value} end\n end ; instance'))

    def get(name, local=0):
        return f'getlocal {local}\ngetproperty {q(name)}'

    def set_(name, value):
        return f'getlocal0\n{value}\nsetproperty {q(name)}'

    def call(name):
        return f'getlocal0\ncallpropvoid {q(name)}, 0'

    fields = [('cursorPlayer', 'int', 'readInt'), ('cursorCharacter', 'int', 'readInt'),
              ('cursorTick', 'uint', 'readUnsignedInt'), ('cursorX', 'Number', 'readFloat'),
              ('cursorY', 'Number', 'readFloat'), ('cursorFire', 'uint', 'readUnsignedByte')]
    for name, type_, _ in fields:
        slot(packet, name, type_, 'Integer(0)')
        slot(game, name, type_, 'Integer(0)')
    for name, type_, value in [('cursorAttached', 'Boolean', 'False()'),
                               ('cursorReady', 'Boolean', 'False()'),
                               ('cursorHasTick', 'Boolean', 'False()'),
                               ('cursorTracePending', 'Boolean', 'False()'),
                               ('cursorTime', 'int', 'Integer(0)'),
                               ('cursorShape', 'Object', 'Null()')]:
        slot(game, name, type_, value)

    # Null-class registration uses the protocol's existing base-message pool, not a new ABC class.
    replace_method(network, '', f'''getlocal0
    getproperty {q('_-08')}
    pushshort 250
    pushnull
    getlocal0
    getproperty {q('spectatorCursor')}
    callpropvoid {q('_-g9')}, 3''', suffix=True, constructor=True)
    add_method(network, 'spectatorCursor', [q('_-098', 'com.company.net')], f'''getlocal0
    pushscope
    {get('gs_')}
    getlocal1
    callpropvoid {q('spectatorCursor')}, 1
    returnvoid''')

    parse = f'''getlocal0
    pushscope
    {get('id_')}
    pushshort 250
    ifne done
    {get('bytesAvailable', 1)}
    pushbyte 21
    ifne invalid
    '''
    for name, _, read in fields:
        parse += set_(name, f'getlocal1\ncallproperty {q(read)}, 0') + '\n'
    for name in ['cursorX', 'cursorY']:
        parse += f'findpropstrict {q("isFinite")}\n{get(name)}\ncallproperty {q("isFinite")}, 1\niffalse invalid\n'
    parse += f'''{get('cursorFire')}
    pushbyte 1
    ifgt invalid
    done:
    returnvoid
    invalid:
    {status('error', 'Invalid cursor packet250: expected21bytes finite x/y fire0/1')}
    findpropstrict {q('Error')}
    pushstring "Invalid spectator cursor packet250"
    constructprop {q('Error')}, 1
    throw'''
    add_method(packet, 'spectatorCursorParse', [q('IDataInput', 'flash.utils')], parse)
    replace_method(packet, 'parseFromInput', f'''getlocal0
    pushscope
    getlocal0
    getlocal1
    callpropvoid {q('spectatorCursorParse')}, 1
    returnvoid''')

    add_method(game, 'spectatorCursorReset', [], f'''getlocal0
    pushscope
    {set_('cursorAttached', 'pushfalse')}
    {set_('cursorReady', 'pushfalse')}
    {set_('cursorHasTick', 'pushfalse')}
    {set_('cursorTracePending', 'pushfalse')}
    {get('cursorShape')}
    iffalse done
    {get('cursorShape')}
    pushfalse
    setproperty {q('visible')}
    done:
    returnvoid''')
    add_method(game, 'spectatorCursorAttach', [q('int'), q('int')], f'''getlocal0
    pushscope
    {call('spectatorCursorReset')}
    {set_('cursorPlayer', 'getlocal1')}
    {set_('cursorCharacter', 'getlocal2')}
    {set_('cursorAttached', 'pushtrue')}
    returnvoid''', locals_=3)
    reset = f'''{get('gs_')}
    callpropvoid {q('spectatorCursorReset')}, 0'''
    for name in ['_-ju', '_-X3', '_-038', '_-of', 'onError', '_-nc']:
        replace_method(network, name, reset, prefix=True)
    replace_method(game, 'onRemovedFromStage', call('spectatorCursorReset'), prefix=True)
    replace_method(network, '_-cw', f'''{get('gs_')}
    {get('objectId_', 1)}
    {get('charId_', 1)}
    callpropvoid {q('spectatorCursorAttach')}, 2''', prefix=True)

    consume = f'''getlocal0
    pushscope
    {get('cursorAttached')}
    iffalse identity
    {get('cursorPlayer', 1)}
    {get('cursorPlayer')}
    ifne identity
    {get('cursorCharacter', 1)}
    {get('cursorCharacter')}
    ifne identity
    {get('cursorHasTick')}
    iffalse accept
    {get('cursorTick', 1)}
    {get('cursorTick')}
    subtract
    convert_u
    setlocal2
    getlocal2
    pushbyte 0
    ifeq stale
    getlocal2
    pushuint 2147483648
    ifge stale
    accept:
    '''
    for name, _, _ in fields[2:]:
        consume += set_(name, get(name, 1)) + '\n'
    timer = f'findpropstrict {q("getTimer", "flash.utils")}\ncallproperty {q("getTimer", "flash.utils")}, 0'
    consume += f'''{set_('cursorTime', timer)}
    {set_('cursorReady', 'pushtrue')}
    {set_('cursorHasTick', 'pushtrue')}
    {set_('cursorTracePending', 'pushtrue')}
    returnvoid
    stale:
    {set_('cursorReady', 'pushfalse')}
    {status('error', 'Stale cursor tick')}
    returnvoid
    identity:
    {call('spectatorCursorReset')}
    {status('error', 'Cursor attachment identity mismatch')}
    returnvoid'''
    add_method(game, 'spectatorCursor', [q('_-098', 'com.company.net')], consume, locals_=3)

    # This runs even without a player, so death/removal cannot leave the last marker on screen.
    replace_method(game, 'onEnterFrame', f'''{get('cursorShape')}
    iffalse cursorHidden
    {get('cursorShape')}
    pushfalse
    setproperty {q('visible')}
    cursorHidden:''', prefix=True)
    # draw uses the camera matrix after the same native camera/map update as every world object.
    anchor = f'      callpropvoid {q("draw")}, 2\n'
    text = game.read_text()
    if text.count(anchor) != 1:
        raise RuntimeError('Expected one spectator map draw')
    game.write_text(text.replace(anchor, anchor + instructions(f'''getlocal0
    getlocal2
    callpropvoid {q('spectatorCursorDraw')}, 1''')))

    shape = f'findpropstrict {q("Shape", "flash.display")}\nconstructprop {q("Shape", "flash.display")}, 0'
    draw = f'''getlocal0
    pushscope
    {get('cursorAttached')}
    iffalse done
    {get('cursorReady')}
    iffalse done
    getlocal1
    {get('cursorTime')}
    subtract
    convert_u
    pushshort 1000
    ifge done
    {get('map_')}
    getproperty {q('player_')}
    setlocal2
    getlocal2
    iffalse done
    {get('objectId_', 2)}
    {get('cursorPlayer')}
    ifne changed
    {get('map_', 2)}
    {get('map_')}
    ifne changed
    {get('map_')}
    getproperty {q('goDict_')}
    {get('cursorPlayer')}
    getproperty MultinameL([PackageNamespace("")])
    getlocal2
    ifne changed
    {get('_-aY', 2)}
    pushbyte 0
    ifle changed
    {get('_-on')}
    getproperty {q('wToS_')}
    findpropstrict {q('Vector3D', 'flash.geom')}
    {get('cursorX')}
    {get('cursorY')}
    pushbyte 0
    constructprop {q('Vector3D', 'flash.geom')}, 3
    callproperty {q('transformVector')}, 1
    setlocal3
    {get('_-on')}
    getproperty {q('_-FL')}
    {get('x', 3)}
    {get('y', 3)}
    callproperty {q('contains')}, 2
    iffalse done
    {get('cursorShape')}
    iftrue shape
    {set_('cursorShape', shape)}
    {get('map_')}
    {get('cursorShape')}
    callpropvoid {q('addChild')}, 1
    shape:
    {get('cursorShape')}
    pushtrue
    setproperty {q('visible')}
    {get('cursorShape')}
    {get('x', 3)}
    setproperty {q('x')}
    {get('cursorShape')}
    {get('y', 3)}
    setproperty {q('y')}
    {get('cursorShape')}
    getproperty {q('graphics')}
    setlocal 4
    getlocal 4
    callpropvoid {q('clear')}, 0
    pushint 16777215
    setlocal 5
    {get('cursorFire')}
    iffalse color
    pushint 16744448
    setlocal 5
    color:
    getlocal 4
    pushbyte 2
    getlocal 5
    pushbyte 1
    callpropvoid {q('lineStyle')}, 3
    getlocal 4
    pushbyte 0
    pushbyte 0
    pushbyte 5
    callpropvoid {q('drawCircle')}, 3
    '''
    for method, x, y in [('moveTo', -9, 0), ('lineTo', -3, 0), ('moveTo', 3, 0),
                          ('lineTo', 9, 0), ('moveTo', 0, -9), ('lineTo', 0, -3),
                          ('moveTo', 0, 3), ('lineTo', 0, 9)]:
        draw += f'getlocal 4\npushbyte {x}\npushbyte {y}\ncallpropvoid {q(method)}, 2\n'
    draw += f'''{get('cursorTracePending')}
    iffalse done
    getlocal1
    {get('spectatorFrameTime')}
    subtract
    pushshort 1000
    iflt done
    {get('map_')}
    findpropstrict {q('Point', 'flash.geom')}
    {get('x', 3)}
    {get('y', 3)}
    constructprop {q('Point', 'flash.geom')}, 2
    callproperty {q('localToGlobal')}, 1
    setlocal3
    {set_('cursorTracePending', 'pushfalse')}
    findpropstrict {q('trace')}
    pushstring "openrotmg-spectator:cursor"
    '''
    for name, local in [(name, 0) for name, _, _ in fields[:-1]] + [('x', 3), ('y', 3), ('cursorFire', 0)]:
        draw += f'pushstring ":"\nadd\n{get(name, local)}\nadd\n'
    draw += f'''callpropvoid {q('trace')}, 1
    done:
    returnvoid
    changed:
    {call('spectatorCursorReset')}
    returnvoid'''
    add_method(game, 'spectatorCursorDraw', [q('int')], draw, locals_=6)

    # Source transitions must invalidate the attachment even when an object ID is reused.
    text = game.read_text()
    anchor = f'      setproperty {q("spectatorSource")}\n'
    if text.count(anchor) != 1:
        raise RuntimeError('Expected one spectator source binding')
    game.write_text(text.replace(anchor, anchor + instructions(f'''getlocal2
    pushbyte -1
    ifeq cursorSourceGone
    getlocal2
    {get('cursorPlayer')}
    ifeq cursorSourceBound
    cursorSourceGone:
    {call('spectatorCursorReset')}
    cursorSourceBound:''')))
