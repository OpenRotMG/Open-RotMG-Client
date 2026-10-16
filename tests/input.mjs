import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

async function setup() {
  class Target {
    listeners = [];
    addEventListener(type, handler, capture = false) { this.listeners.push({type, handler, capture}); }
    dispatchEvent(event) {
      for (const capture of [true, false]) {
        for (const listener of this.listeners) {
          if (listener.type === event.type && listener.capture === capture) listener.handler(event);
        }
      }
    }
  }
  class KeyboardEvent {
    constructor(type, init) { Object.assign(this, init, {type}); }
  }
  const window = new Target(), player = new Target(), child = {}, delivered = [];
  let focused = true;
  player.contains = target => target === player || target === child;
  player.ruffle = () => ({load: async () => {
    player.addEventListener('focusout', event => { if (!player.contains(event.relatedTarget)) focused = false; });
    window.addEventListener('keyup', event => { if (focused) delivered.push(event); });
  }});
  window.RufflePlayer = {newest: () => ({createPlayer: () => player})};
  const document = {querySelector: selector => ({'#client': {append() {}}, '#status': {}})[selector]};
  await vm.runInNewContext(script, {window, document, KeyboardEvent, URL, location: {href:'http://localhost:8080/'}, console});
  const down = (code, key, extra = {}) => player.dispatchEvent({type:'keydown', code, key, ...extra});
  const up = (code, key) => {
    const event = new KeyboardEvent('keyup', {code, key});
    player.dispatchEvent(event); window.dispatchEvent(event);
  };
  const blur = () => window.dispatchEvent({type:'blur'});
  const focusout = relatedTarget => player.dispatchEvent({type:'focusout', relatedTarget});
  return {window, player, child, delivered, down, up, blur, focusout};
}

test('held movement, rotation and ability keys release before Ruffle loses focus', async () => {
  const t = await setup();
  for (const [code, key] of [['KeyW','w'], ['KeyQ','q'], ['Space',' ']]) t.down(code, key);
  t.focusout(null);
  assert.deepEqual(t.delivered.map(e => [e.code, e.key]), [['KeyW','w'], ['KeyQ','q'], ['Space',' ']]);
  assert.equal(t.player.listeners.find(e => e.type === 'focusout').capture, true);
});

test('released keys and auto-repeat do not generate duplicate releases', async () => {
  const t = await setup();
  t.down('KeyW', 'w'); t.up('KeyW', 'w');
  t.down('KeyD', 'd'); t.down('KeyD', 'd', {repeat:true});
  t.blur(); t.blur();
  assert.deepEqual(t.delivered.map(e => e.code), ['KeyW', 'KeyD']);
});

test('focus movement inside Ruffle does not release gameplay keys', async () => {
  const t = await setup();
  t.down('KeyA', 'a'); t.focusout(t.child);
  assert.equal(t.delivered.length, 0);
  t.blur();
  assert.equal(t.delivered[0].code, 'KeyA');
});

test('focusout followed by window blur releases each key only once', async () => {
  const t = await setup();
  t.down('KeyS', 's'); t.focusout(null); t.blur();
  assert.equal(t.delivered.length, 1);
});

test('a release handler causing another blur does not release keys recursively', async () => {
  const t = await setup();
  t.window.addEventListener('keyup', t.blur);
  t.down('KeyW', 'w'); t.blur();
  assert.equal(t.delivered.length, 1);
});

test('physical key location and legacy key code survive cancellation', async () => {
  const t = await setup();
  t.down('ShiftLeft', 'Shift', {location:1, keyCode:16});
  t.down('ShiftRight', 'Shift', {location:2, keyCode:16}); t.blur();
  assert.deepEqual(t.delivered.map(e => [e.code, e.location, e.keyCode]), [['ShiftLeft',1,16], ['ShiftRight',2,16]]);
});

test('keys outside the player are not captured', async () => {
  const t = await setup();
  t.window.dispatchEvent({type:'keydown', code:'KeyW', key:'w'}); t.blur();
  assert.equal(t.delivered.length, 0);
});
