"""Show only the observed bot's actual public composition in the native chat field."""
from build_spectator import add_method, private, q, replace_method, status


def transform(root):
    game = root / 'com/company/assembleegameclient/game/GameSprite.class.asasm'
    network = root / 'com/company/assembleegameclient/net/_-1f.class.asasm'
    packet = root / 'com/company/net/_-098.class.asasm'
    chat = root / 'com/company/assembleegameclient/ui/_-4D.class.asasm'
    def get(name, local=0):
        return f'getlocal {local}\ngetproperty {q(name)}'
    def set_(name, code):
        return f'getlocal0\n{code}\nsetproperty {q(name)}'
    def apply(phase, text):
        return f'{get("textBox_")}\n{phase}\n{text}\ncallpropvoid {q("spectatorCompose")}, 2'
    fields = [('chatPlayer', 'int', 'readInt'), ('chatCharacter', 'int', 'readInt'),
              ('chatTick', 'uint', 'readUnsignedInt'), ('chatPhase', 'uint', 'readUnsignedByte'),
              ('chatDraft', 'String', 'readUTF')]
    for path in [packet, game]:
        text = path.read_text()
        slots = ''.join(f'  trait slot {q(name)} type {q(type_)} end\n' for name, type_, _ in fields)
        if path == game:
            slots += ''.join(f'  trait slot {q(name)} type {q(type_)} value {value} end\n' for name, type_, value in [
                ('chatHasTick', 'Boolean', 'False()'), ('chatReady', 'Boolean', 'False()'),
                ('chatTracePending', 'Boolean', 'False()'), ('chatTime', 'int', 'Integer(0)')])
        if text.count(' end ; instance') != 1:
            raise RuntimeError(f'Expected one chat input instance: {path}')
        path.write_text(text.replace(' end ; instance', slots + ' end ; instance'))
    replace_method(network, '', f'''getlocal0
    getproperty {q('_-08')}
    pushshort 251
    pushnull
    getlocal0
    getproperty {q('spectatorChat')}
    callpropvoid {q('_-g9')}, 3''', suffix=True, constructor=True)
    add_method(network, 'spectatorChat', [q('_-098', 'com.company.net')], f'''getlocal0
    pushscope
    {get('gs_')}
    getlocal1
    callpropvoid {q('spectatorChat')}, 1
    returnvoid''')
    parse = f'''getlocal0
    pushscope
    {get('id_')}
    pushshort 251
    ifne done
    {get('bytesAvailable', 1)}
    pushbyte 15
    iflt invalid
    {get('bytesAvailable', 1)}
    pushshort 527
    ifgt invalid
    '''
    for name, _, read in fields:
        parse += set_(name, f'getlocal1\ncallproperty {q(read)}, 0') + '\n'
    parse += f'''{get('bytesAvailable', 1)}
    pushbyte 0
    ifne invalid
    {get('chatPhase')}
    pushbyte 2
    ifgt invalid
    {get('chatDraft')}
    getproperty {q('length')}
    pushshort 256
    ifgt invalid
    {get('chatDraft')}
    pushbyte 0
    callproperty {q('charAt')}, 1
    pushstring "/"
    ifeq invalid
    {get('chatPhase')}
    iftrue done
    {get('chatDraft')}
    pushstring ""
    ifne invalid
    done:
    returnvoid
    invalid:
    {status('error', 'Invalid public composition packet251')}
    findpropstrict {q('Error')}
    pushstring "Invalid spectator composition packet251"
    constructprop {q('Error')}, 1
    throw'''
    add_method(packet, 'spectatorChatParse', [q('IDataInput', 'flash.utils')], parse)
    replace_method(packet, 'parseFromInput', f'''getlocal0
    getlocal1
    callpropvoid {q('spectatorChatParse')}, 1''', prefix=True)
    add_method(game, 'spectatorChatReset', [], f'''getlocal0
    pushscope
    {set_('chatHasTick', 'pushfalse')}
    {set_('chatReady', 'pushfalse')}
    {set_('chatTracePending', 'pushfalse')}
    {apply('pushbyte 0', 'pushstring ""')}
    returnvoid''')
    consume = f'''getlocal0
    pushscope
    {get('cursorAttached')}
    iffalse identity
    {get('chatPlayer', 1)}
    {get('cursorPlayer')}
    ifne identity
    {get('chatCharacter', 1)}
    {get('cursorCharacter')}
    ifne identity
    {get('chatHasTick')}
    iffalse accept
    {get('chatTick', 1)}
    {get('chatTick')}
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
    {get('chatReady')}
    iffalse changed
    {get('chatPhase', 1)}
    {get('chatPhase')}
    ifne changed
    {get('chatDraft', 1)}
    {get('chatDraft')}
    ifeq copy
    changed:
    {set_('chatTracePending', 'pushtrue')}
    copy:
    '''
    for name, _, _ in fields:
        consume += set_(name, get(name, 1)) + '\n'
    timer = f'findpropstrict {q("getTimer", "flash.utils")}\ncallproperty {q("getTimer", "flash.utils")}, 0'
    consume += f'''{set_('chatTime', timer)}
    {set_('chatHasTick', 'pushtrue')}
    {set_('chatReady', 'pushtrue')}
    {apply(get('chatPhase'), get('chatDraft'))}
    returnvoid
    stale:
    {set_('chatReady', 'pushfalse')}
    {apply('pushbyte 0', 'pushstring ""')}
    {status('error', 'Stale composition tick')}
    returnvoid
    identity:
    getlocal0
    callpropvoid {q('spectatorCursorReset')}, 0
    {status('error', 'Composition attachment identity mismatch')}
    returnvoid'''
    add_method(game, 'spectatorChat', [q('_-098', 'com.company.net')], consume, locals_=3)
    add_method(game, 'spectatorChatExpire', [], f'''getlocal0
    pushscope
    {get('chatReady')}
    iffalse done
    {timer}
    {get('chatTime')}
    subtract
    convert_u
    pushshort 1000
    iflt done
    {set_('chatReady', 'pushfalse')}
    {set_('chatTracePending', 'pushfalse')}
    {apply('pushbyte 0', 'pushstring ""')}
    done:
    returnvoid''')
    trace = f'''getlocal0
    pushscope
    {get('cursorAttached')}
    iffalse done
    {get('chatReady')}
    iffalse done
    {get('chatTracePending')}
    iffalse done
    {set_('chatTracePending', 'pushfalse')}
    findpropstrict {q('trace')}
    pushstring "openrotmg-spectator:compose"
    '''
    for name, _, _ in fields:
        trace += f'pushstring ":"\nadd\n{get(name)}\nadd\n'
    trace += f'''callpropvoid {q('trace')}, 1
    done:
    returnvoid'''
    add_method(game, 'spectatorChatDraw', [q('int')], trace)
    field = private('_-bn', 'com.company.assembleegameclient.ui:_-4D#0')
    layout = private('_-KC', 'com.company.assembleegameclient.ui:_-4D#0')
    # Reuse the native field/layout without focus or input handlers: spectators cannot type into a bot.
    add_method(chat, 'spectatorCompose', [q('uint'), q('String')], f'''getlocal0
    pushscope
    getlocal0
    getproperty {field}
    setlocal3
    getlocal3
    pushstring "dynamic"
    setproperty {q('type')}
    getlocal3
    pushfalse
    setproperty {q('selectable')}
    getlocal3
    getlocal2
    setproperty {q('text')}
    getlocal0
    getlocal3
    callproperty {q('contains')}, 1
    setlocal 4
    getlocal1
    iffalse closed
    getlocal 4
    iftrue layout
    getlocal0
    getlocal3
    callpropvoid {q('addChild')}, 1
    jump layout
    closed:
    getlocal 4
    iffalse layout
    getlocal0
    getlocal3
    callpropvoid {q('removeChild')}, 1
    layout:
    getlocal0
    callpropvoid {layout}, 0
    returnvoid''', locals_=5)
