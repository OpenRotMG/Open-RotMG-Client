import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
import {createHash} from 'node:crypto';

const script = await readFile(new URL('../spectator.js', import.meta.url), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const reply = (body, status = 200) => ({ok: status === 200, status, text: async () => JSON.stringify(body)});
async function launch({path = '/api/bots/Triceps/view', ruffle = true, loadError, resolve = () => reply({bot:'Biceps', player:22, source:11})} = {}) {
  let now = 0, options, refresh, nextTimer = 0;
  const messages = [], requests = [], errors = [], cursorTraces = [], events = {}, eventOptions = {}, status = {}, timers = new Map();
  const button = {addEventListener: (name, fn) => {button[name] = fn;}};
  const menu = {hidden:true, style:{}, offsetWidth:150, offsetHeight:44,
    querySelector: () => button, contains: element => element === button};
  const inspectStatus = {};
  const client = {append() {}, getBoundingClientRect: () => ({left:40, top:20, width:400, height:300, right:440, bottom:320})};
  const api = {load: async value => {
    options = value;
    if (loadError) throw new Error(loadError);
  }}, player = {ruffle: () => api};
  const window = {parent: {postMessage: message => messages.push(message)},
    addEventListener: (name, callback, options) => {events[name] = callback;eventOptions[name] = options;},
    setInterval: callback => {refresh = callback; return 1;}, clearInterval() {},
    setTimeout: (fn, ms) => {timers.set(++nextTimer, {fn, due:now+ms}); return nextTimer;},
    clearTimeout: id => timers.delete(id)};
  if (ruffle) window.RufflePlayer = {newest: () => ({createPlayer: () => player})};
  await vm.runInNewContext(script, {window, document: {querySelector: selector => ({'#status':status, '#perspective':menu, '#inspect-status':inspectStatus, '#client':client})[selector]},
    performance: {now: () => now}, location: {pathname: path, href: `https://game.example${path}`, protocol: 'https:'}, URL, AbortController,
    fetch: (url, opts) => {requests.push({url, options:opts}); return resolve(url, opts);},
    console: {error: error => errors.push(error), warn: error => errors.push(error), debug: message => cursorTraces.push(message)}});
  return {window, options, messages, events, status, menu, button, inspectStatus, requests, errors, cursorTraces,
    advance: ms => {now += ms; for (const [id,timer] of timers) if (timer.due <= now) {timers.delete(id); timer.fn();} refresh();},
    pointerDown: async () => {
      const event = {target: {}};
      if (eventOptions.pointerdown === true) events.pointerdown(event);
      api.traceObserver('openrotmg-spectator:inspect:11:22:320:240');
      if (eventOptions.pointerdown !== true) events.pointerdown(event);
      await flush();
    },
    click: () => button.click(), trace: message => api.traceObserver(message),
    inspect: async (from=11, target=22, x=320, y=240) => {api.traceObserver(`openrotmg-spectator:inspect:${from}:${target}:${x}:${y}`); await flush();},
    live: () => {api.traceObserver('openrotmg-spectator:source:11'); api.traceObserver('openrotmg-spectator:tick:'); api.traceObserver('openrotmg-spectator:frame:');},
    native: (state, error = '') => api.traceObserver(`openrotmg-spectator:${state}:${error}`)};
}

test('fixed same-origin assets/socket, selected native HUD flashvar, responsive 800x600 ratio', async () => {
  const {options, messages} = await launch();
  const lock = JSON.parse(await readFile(new URL('../spectator/lock.json', import.meta.url), 'utf8'));
  assert.equal(options.url, `/api/bots/client.swf?v=${lock.outputSha256}`);
  assert.equal(options.parameters.bot, 'Triceps');
  assert.equal(options.socketProxy.length, 1);
  assert.equal(options.socketProxy[0].proxyUrl, 'wss://game.example/api/bots/Triceps/socket?cursor=2');
  assert.equal(options.contextMenu, 'off');
  assert.equal(options.openUrlMode, 'deny');
  assert.equal(options.allowScriptAccess, false);
  assert.equal(options.urlRewriteRules.length, 2);
  assert.equal(options.urlRewriteRules[0][1], 'https://game.example/sfx/');
  assert.equal(options.urlRewriteRules[1][1], 'https://game.example/sfx/music/');
  assert.equal(messages[0].type, 'openrotmg-bot-view');
  assert.equal(messages[0].bot, 'Triceps');
  const html = await readFile(new URL('../spectator.html', import.meta.url), 'utf8');
  assert.ok(html.includes(`/api/bots/spectator.js?v=${createHash('sha256').update(script).digest('hex')}`), 'viewer must invalidate the cached script when it changes');
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

test('native cursor draw traces remain observable without substituting for frame/tick acceptance', async () => {
  const view = await launch();
  const trace = 'openrotmg-spectator:cursor:11:7:42:2.25:-3.5:295:302.5:1';
  view.trace(trace);
  assert.deepEqual(view.cursorTraces, [trace]);
  assert.equal(view.messages.at(-1).status, 'connecting');
  view.native('tick');
  view.trace(trace);
  assert.equal(view.messages.at(-1).status, 'connecting');
  view.native('frame');
  assert.equal(view.messages.at(-1).status, 'live');
  assert.equal(view.errors.length, 0);
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

test('native actor inspection resolves read-only, scales/clamps menu and posts exact parent selection', async () => {
  const view = await launch();
  await view.inspect();
  assert.equal(view.requests.length, 0, 'no native source/liveness, no lookup');
  view.live();
  await view.inspect();
  assert.equal(view.requests.length, 1);
  const request = view.requests[0];
  assert.equal(request.url, '/api/bots/Triceps/perspective/22?source=11');
  assert.equal(request.options.method, 'GET');
  assert.equal(request.options.credentials, 'omit');
  assert.equal(request.options.mode, 'same-origin');
  assert.equal(request.options.redirect, 'error');
  assert.equal(request.options.cache, 'no-store');
  assert.equal(view.menu.hidden, false);
  assert.equal(view.menu.style.left, '200px');
  assert.equal(view.menu.style.top, '140px');
  await view.click();
  assert.deepEqual(JSON.parse(JSON.stringify(view.messages.at(-1))), {type:'openrotmg-bot-select', bot:'Triceps', target:'Biceps'});
  assert.equal(view.menu.hidden, true);
  const count = view.messages.length;
  await view.click();
  assert.equal(view.messages.length, count, 'selection is single use');
  await view.inspect(11,22,800,600);
  assert.equal(view.menu.style.left, '290px');
  assert.equal(view.menu.style.top, '276px');
});

test('outside-menu capture runs before the canvas native trace, not after its lookup', async () => {
  const view = await launch();view.live();
  await view.pointerDown();
  assert.equal(view.requests.length, 1);
  assert.equal(view.requests[0].options.signal.aborted, false);
  assert.equal(view.menu.hidden, false);
  await view.click();
  assert.equal(view.messages.at(-1).type, 'openrotmg-bot-select');
});

test('human, malformed, private-field and mismatched resolver replies never offer perspective', async () => {
  for (const response of [reply(null,404), reply(null,403), reply({bot:'Biceps',player:23,source:11}),
    reply({bot:'Biceps',player:22,source:12}), reply({bot:'../',player:22,source:11}),
    reply({bot:'Biceps',player:22,source:11,account:'private'}), reply('x'.repeat(1100)),
    {ok:true,status:200,text:async () => '{'}]) {
    const view = await launch({resolve: () => response});
    view.live();
    await view.inspect();
    assert.equal(view.menu.hidden, true);
    await view.click();
    assert.ok(view.messages.every(message => message.type !== 'openrotmg-bot-select'));
    if (response.status !== 404) assert.ok(view.errors.length > 0);
  }
});

test('malformed, out-of-bounds, self and stale-source traces never query; requests are rate bounded', async () => {
  const view = await launch(); view.live();
  for (const args of [[12,22], [11,11], [-1,22], [11,2147483648], [11,22,801,1], [11,22,1,601],
    [11,22,'NaN',1], [11,22,1,'Infinity'], [11,22,-1,0]]) await view.inspect(...args);
  assert.equal(view.requests.length, 0);
  for (let i=0;i<10;i++) await view.inspect();
  assert.equal(view.requests.length, 4);
  assert.match(view.inspectStatus.textContent, /rate limited/);
  view.advance(1000); view.native('tick'); view.native('frame');
  await view.inspect();
  assert.equal(view.requests.length, 5);
});

test('source changes, reconnect, runtime state, dismissal, expiry and pagehide invalidate menus and late responses', async () => {
  const invalidate = [v => v.trace('openrotmg-spectator:source:12'), v => v.trace('openrotmg-spectator:source:-1'),
    v => v.native('connecting'), v => v.native('disconnected'), v => v.native('error','socket'),
    v => v.trace('openrotmg-spectator:source:malformed'), v => v.events.resize(),
    v => v.events.pointerdown({target:{}}), v => v.events.keydown({key:'Escape'}), v => v.events.pagehide()];
  for (const clear of invalidate) {
    let finish;
    const view = await launch({resolve: () => new Promise(resolve => {finish = resolve;})});
    view.live(); await view.inspect();
    clear(view);
    assert.equal(view.requests[0].options.signal.aborted, true);
    finish(reply({bot:'Biceps',player:22,source:11})); await flush();
    assert.equal(view.menu.hidden, true);
    await view.click();
    assert.ok(view.messages.every(message => message.type !== 'openrotmg-bot-select'));
  }
  const view = await launch(); view.live(); await view.inspect();
  view.advance(5000);
  assert.equal(view.menu.hidden, true);
  view.live(); await view.inspect();
  view.events.pointerdown({target:view.button});
  assert.equal(view.menu.hidden, false, 'menu pointerdown does not dismiss before selection');
});

test('newest click wins even if aborted fetch ignores cancellation; lookup timeout is observable', async () => {
  const pending = [];
  const view = await launch({resolve: () => new Promise(resolve => pending.push(resolve))});
  view.live(); await view.inspect(); await view.inspect(11,23);
  pending[1](reply({bot:'Other',player:23,source:11})); await flush();
  pending[0](reply({bot:'Biceps',player:22,source:11})); await flush();
  const selecting = view.click();
  pending[2](reply({bot:'Other',player:23,source:11})); await selecting;
  assert.equal(view.messages.at(-1).target, 'Other');
  const timeout = await launch({resolve: (_url,opts) => new Promise((_resolve,reject) => opts.signal.addEventListener('abort', () => reject(new Error('aborted'))))});
  timeout.live(); await timeout.inspect(); timeout.advance(3000); await flush();
  assert.match(timeout.inspectStatus.textContent, /timed out/);
  assert.equal(timeout.menu.hidden, true);
});

test('selection re-resolves exact actor/profile identity and never follows reused IDs or stale replies', async () => {
  for (const changed of [reply({bot:'ReusedId',player:22,source:11}), reply(null,404),
    reply({bot:'Biceps',player:23,source:11}), reply({bot:'Biceps',player:22,source:12})]) {
    let calls = 0;
    const view = await launch({resolve: () => ++calls === 1 ? reply({bot:'Biceps',player:22,source:11}) : changed});
    view.live(); await view.inspect(); await view.click();
    assert.equal(view.requests.length, 2);
    assert.equal(view.requests[0].url, view.requests[1].url);
    assert.ok(view.messages.every(message => message.type !== 'openrotmg-bot-select'));
    assert.ok(view.errors.length > 0);
  }
  let finish, calls = 0;
  const view = await launch({resolve: () => ++calls === 1 ? reply({bot:'Biceps',player:22,source:11}) : new Promise(resolve => {finish=resolve;})});
  view.live(); await view.inspect(); const selecting = view.click();
  view.native('connecting');
  finish(reply({bot:'Biceps',player:22,source:11})); await selecting;
  assert.ok(view.messages.every(message => message.type !== 'openrotmg-bot-select'));
});

test('invalid paths/names fail without loading arbitrary movies or sockets', async () => {
  for (const path of ['/api/bots/Triceps/view/extra', '/api/bots/%2f/view', '/api/bots/%ZZ/view', '/api/bots/../view']) {
    const view = await launch({path});
    assert.equal(view.options, undefined);
    assert.match(view.status.textContent, /^error:/);
  }
});
