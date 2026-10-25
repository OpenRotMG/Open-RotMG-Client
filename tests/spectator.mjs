import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const script = await readFile(new URL('../spectator.js', import.meta.url), 'utf8');
async function launch({path = '/api/bots/Triceps/view', ruffle = true, loadError} = {}) {
  let now = 0, options, refresh;
  const messages = [], events = {}, status = {}, api = {load: async value => {
    options = value;
    if (loadError) throw new Error(loadError);
  }}, player = {ruffle: () => api};
  const window = {parent: {postMessage: message => messages.push(message)},
    addEventListener: (name, callback) => {events[name] = callback;},
    setInterval: callback => {refresh = callback; return 1;}, clearInterval() {}};
  if (ruffle) window.RufflePlayer = {newest: () => ({createPlayer: () => player})};
  await vm.runInNewContext(script, {window, document: {querySelector: selector => selector === '#status' ? status : {append() {}}},
    performance: {now: () => now}, location: {pathname: path, href: `https://game.example${path}`, protocol: 'https:'}, URL,
    console: {error() {}}});
  return {window, options, messages, events, status, advance: ms => {now += ms; refresh();},
    native: (state, error = '') => api.traceObserver(`openrotmg-spectator:${state}:${error}`)};
}

test('fixed same-origin assets/socket, selected native HUD flashvar, responsive 800x600 ratio', async () => {
  const {options, messages} = await launch();
  assert.equal(options.url, '/api/bots/client.swf');
  assert.equal(options.parameters.bot, 'Triceps');
  assert.equal(options.socketProxy.length, 1);
  assert.equal(options.socketProxy[0].proxyUrl, 'wss://game.example/api/bots/Triceps/socket');
  assert.equal(options.openUrlMode, 'deny');
  assert.equal(options.allowScriptAccess, false);
  assert.equal(options.urlRewriteRules.length, 2);
  assert.equal(options.urlRewriteRules[0][1], 'https://game.example/sfx/');
  assert.equal(options.urlRewriteRules[1][1], 'https://game.example/sfx/music/');
  assert.equal(messages[0].type, 'openrotmg-bot-view');
  assert.equal(messages[0].bot, 'Triceps');
  const html = await readFile(new URL('../spectator.html', import.meta.url), 'utf8');
  assert.match(html, /aspect-ratio:4\/3/);
  assert.match(html, /100vh \* 4 \/ 3/);
  assert.doesNotMatch(html, /launcher.js|<canvas|Play|account|legacy-api/);
});

test('live requires completed native drawing AND ticks, stale requires both to recover', async () => {
  const view = await launch();
  view.native('tick');
  assert.equal(view.messages.at(-1).status, 'connecting');
  view.native('frame');
  assert.equal(view.messages.at(-1).status, 'live');
  view.advance(5000);
  assert.equal(view.messages.at(-1).status, 'stale');
  view.native('frame');
  assert.equal(view.messages.at(-1).status, 'stale');
  view.native('tick');
  assert.equal(view.messages.at(-1).status, 'live');
  view.native('disconnected');
  view.native('tick');
  view.native('frame');
  assert.equal(view.messages.at(-1).status, 'disconnected');
  view.native('connecting');
  view.native('frame');
  assert.equal(view.messages.at(-1).status, 'connecting');
  view.native('tick');
  assert.equal(view.messages.at(-1).status, 'live');
});

test('steady native rendering sends live heartbeats without inventing state changes', async () => {
  const view = await launch();
  view.native('tick');view.native('frame');
  for (let i=0;i<16;i++) {view.native('tick');view.native('frame');view.advance(1000);}
  assert.ok(view.messages.filter(m=>m.status==='live').length>=4);
  assert.equal(view.messages.at(-1).status,'live');
});

test('missing assets, SWF failure, socket error, runtime error and no draw fail observably', async () => {
  for (const options of [{ruffle: false}, {loadError: 'SWF unavailable'}]) {
    const view = await launch(options);
    assert.equal(view.messages.at(-1).status, 'error');
    assert.match(view.messages.at(-1).error, /unavailable/);
  }
  const view = await launch();
  view.native('tick');
  view.advance(15000);
  assert.equal(view.messages.at(-1).status, 'error');
  assert.match(view.messages.at(-1).error, /did not draw/);
  view.native('frame');
  assert.equal(view.messages.at(-1).status, 'error');
  view.native('connecting');
  view.native('error', 'Admission denied');
  assert.equal(view.messages.at(-1).error, 'Admission denied');
  view.events.unhandledrejection({reason: new Error('Runtime failure')});
  assert.equal(view.messages.at(-1).error, 'Runtime failure');
});

test('invalid paths/names fail without loading arbitrary movies or sockets', async () => {
  for (const path of ['/api/bots/Triceps/view/extra', '/api/bots/%2f/view', '/api/bots/%ZZ/view', '/api/bots/../view']) {
    const view = await launch({path});
    assert.equal(view.options, undefined);
    assert.match(view.status.textContent, /^error:/);
  }
});
