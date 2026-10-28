import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
import {createHash} from 'node:crypto';

const script = await readFile(new URL('../spectator.js', import.meta.url), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const reply = (body, status = 200) => ({ok: status === 200, status, text: async () => JSON.stringify(body)});
async function launch({path = '/api/bots/Triceps/view', ruffle = true, loadError, loadDelay = 0, duringLoadSwitch = false, resolve = () => reply({bot:'Biceps', player:22, source:11})} = {}) {
  let now = 0, options, refresh, nextTimer = 0, control, creates = 0, loads = 0;
  const sent = [], sockets = [];
  class WebSocket {
    static OPEN = 1;
    constructor(url) {
      this.readyState = 1;control = this;sockets.push(url);
      queueMicrotask(() => this.message({type:'ready',view:'1'.repeat(32),bot:'Triceps',generation:0,parent_origin:'https://site.example'}));
    }
    message(data) {this.onmessage({data:JSON.stringify(data)});}
    send(data) {sent.push(JSON.parse(data));}
    close() {this.readyState = 3;}
  }
  const messages = [], requests = [], errors = [], cursorTraces = [], events = {}, eventOptions = {}, status = {}, timers = new Map();
  const button = {addEventListener: (name, fn) => {button[name] = fn;}};
  const menu = {hidden:true, style:{}, offsetWidth:150, offsetHeight:44,
    querySelector: () => button, contains: element => element === button};
  const inspectStatus = {};
  const client = {append() {}, getBoundingClientRect: () => ({left:40, top:20, width:400, height:300, right:440, bottom:320})};
  const api = {load: async value => {
    options = value;loads++;
    if (duringLoadSwitch) {
      events.message({origin:'https://site.example',source:window.parent,data:{type:'openrotmg-bot-watch',bot:'Biceps',generation:1,target:{kind:'bot',bot:'Biceps'}}});
      control.message({type:'selected',bot:'Biceps',generation:1});
    }
    if (loadDelay) {now += loadDelay;refresh();}
    if (loadError) throw new Error(loadError);
  }}, player = {ruffle: () => api};
  const window = {parent: {postMessage: message => messages.push(message)},
    addEventListener: (name, callback, options) => {events[name] = callback;eventOptions[name] = options;},
    setInterval: callback => {refresh = callback; return 1;}, clearInterval() {},
    setTimeout: (fn, ms) => {timers.set(++nextTimer, {fn, due:now+ms}); return nextTimer;},
    clearTimeout: id => timers.delete(id)};
  if (ruffle) window.RufflePlayer = {newest: () => ({createPlayer: () => {creates++;return player;}})};
  await vm.runInNewContext(script, {window, document: {querySelector: selector => ({'#status':status, '#perspective':menu, '#inspect-status':inspectStatus, '#client':client})[selector]},
    WebSocket, performance: {now: () => now}, location: {pathname: path, href: `https://game.example${path}`, protocol: 'https:'}, URL, AbortController,
    fetch: (url, opts) => {requests.push({url, options:opts}); return resolve(url, opts);},
    console: {error: error => errors.push(error), warn: error => errors.push(error), debug: message => cursorTraces.push(message)}});
  const attached = (bot='Triceps', generation=0, player=11, character=7) => control.message({type:'attached',bot,generation,player,character});
  if (api.traceObserver && !errors.length) attached();
  return {window, options, messages, events, status, menu, button, inspectStatus, requests, errors, cursorTraces, sent, sockets, attached,
    control: data => control.message(data), counts: () => ({creates,loads}),
    command: (bot, generation, target={kind:'bot',bot}, origin='https://site.example', source=window.parent) =>
      events.message({origin, source, data:{type:'openrotmg-bot-watch',bot,generation,target}}),
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
    live: () => {api.traceObserver('openrotmg-spectator:source:11'); api.traceObserver('openrotmg-spectator:tick:11'); api.traceObserver('openrotmg-spectator:frame:11');},
    native: (state, error = ['frame','tick'].includes(state) ? '11' : '') => {
      api.traceObserver(`openrotmg-spectator:${state}:${error}`);
      if (state === 'connecting') attached();
    }};
}

test('fixed same-origin assets/socket, selected native HUD flashvar, responsive 800x600 ratio', async () => {
  const {options, messages} = await launch();
  const lock = JSON.parse(await readFile(new URL('../spectator/lock.json', import.meta.url), 'utf8'));
  assert.equal(options.url, `/api/bots/client.swf?v=${lock.outputSha256}`);
  assert.equal(options.parameters.bot, 'Triceps');
  assert.equal(options.socketProxy.length, 1);
  assert.equal(options.socketProxy[0].proxyUrl, `wss://game.example/api/bots/views/${'1'.repeat(32)}/socket?cursor=2`);
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
  const composition = 'openrotmg-spectator:compose:11:7:42:1:wts';
  view.trace(composition);
  assert.deepEqual(view.cursorTraces, [trace, composition]);
  assert.equal(view.messages.at(-1).status, 'connecting');
  view.native('tick');
  view.trace(trace);
  assert.equal(view.messages.at(-1).status, 'connecting');
  view.native('frame');
  assert.equal(view.messages.at(-1).status, 'live');
  assert.equal(view.errors.length, 0);
});

test('cold renderer initialization is bounded separately from the unchanged native first-frame deadline', async () => {
  const view = await launch({loadDelay: 19000});
  assert.equal(view.messages.at(-1).status, 'connecting');assert.equal(view.errors.length, 0);
  view.advance(14999);assert.equal(view.messages.at(-1).status, 'connecting');
  view.advance(1);assert.equal(view.messages.at(-1).status, 'error');
  assert.match(view.messages.at(-1).error, /within 15 seconds/);
  const stuck = await launch({loadDelay: 60000});
  assert.equal(stuck.messages.at(-1).status, 'error');
  assert.match(stuck.messages.at(-1).error, /renderer.*initialize.*60 seconds/i);
  const late = await launch();late.advance(14000);late.attached();late.advance(1000);
  assert.equal(late.messages.at(-1).status,'error','attachment metadata must not extend the native draw deadline');
});

test('switching during cold initialization does not start the native deadline before the renderer is ready', async () => {
  const view = await launch({loadDelay:19000,duringLoadSwitch:true});
  assert.equal(view.messages.at(-1).status,'connecting');assert.equal(view.messages.at(-1).bot,'Biceps');assert.equal(view.errors.length,0);
  view.advance(14999);assert.equal(view.messages.at(-1).status,'connecting');
  view.advance(1);assert.equal(view.messages.at(-1).status,'error');assert.match(view.messages.at(-1).error,/within 15 seconds/);
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
  assert.deepEqual(JSON.parse(JSON.stringify(view.messages.at(-1))), {type:'openrotmg-bot-choice', bot:'Triceps', generation:0, target:'Biceps', source:11, player:22});
  assert.ok(view.messages.some(message => message.type === 'openrotmg-bot-select' && message.target === 'Biceps'));
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
  assert.equal(view.messages.at(-1).type, 'openrotmg-bot-choice');
});

test('unwatchable players show disabled cannot-spy feedback without changing the live view', async () => {
  let response = reply(null,404);
  const view = await launch({resolve: () => response});view.live();await view.inspect();
  assert.equal(view.menu.hidden, false);
  assert.equal(view.button.disabled, true);
  assert.equal(view.button.textContent, 'Player (cannot spy)');
  assert.equal(view.errors.length, 0);
  assert.equal(view.messages.at(-1).status, 'live');
  await view.click();assert.ok(view.messages.every(message => message.type !== 'openrotmg-bot-select'));
  response = reply({bot:'Biceps',player:22,source:11});await view.inspect();
  assert.equal(view.button.disabled, false);assert.equal(view.button.textContent, 'View perspective');
  await view.click();assert.equal(view.messages.at(-1).target, 'Biceps');
});

test('malformed, private-field and mismatched resolver replies never offer perspective', async () => {
  for (const response of [reply(null,403), reply({bot:'Biceps',player:23,source:11}),
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

test('A to B to A reuses one movie and requires fresh matching native actor frame plus tick', async () => {
  const view = await launch();view.live();const proxy = view.options.socketProxy[0].proxyUrl;
  view.command('Biceps',1);
  assert.deepEqual(JSON.parse(JSON.stringify(view.sent)), [{generation:1,target:{kind:'bot',bot:'Biceps'}}]);
  view.native('frame');view.native('tick');assert.equal(view.messages.at(-1).status,'connecting');
  view.control({type:'selected',bot:'Biceps',generation:1});
  view.native('frame','22');view.native('tick','22');assert.equal(view.messages.at(-1).status,'connecting');
  view.attached('Biceps',1,22,8);
  view.native('frame');view.native('tick');assert.equal(view.messages.at(-1).status,'connecting');
  view.native('frame','22');assert.equal(view.messages.at(-1).status,'connecting');
  view.native('tick','22');assert.equal(view.messages.at(-1).status,'live');
  assert.equal(view.messages.at(-1).bot,'Biceps');assert.equal(view.messages.at(-1).generation,1);
  view.command('Triceps',2);view.control({type:'selected',bot:'Triceps',generation:2});
  view.attached('Biceps',1,22,8);view.native('frame','22');view.native('tick','22');
  assert.equal(view.messages.at(-1).status,'connecting');
  view.attached('Triceps',2);view.live();assert.equal(view.messages.at(-1).status,'live');
  assert.equal(view.messages.at(-1).generation,2);assert.equal(view.messages.at(-1).bot,'Triceps');
  assert.equal(view.options.socketProxy[0].proxyUrl,proxy);assert.deepEqual(view.counts(),{creates:1,loads:1});
  assert.equal(view.sockets.length,1);assert.ok(!JSON.stringify(view.messages).includes('1'.repeat(32)));
});

test('watch commands require exact parent origin, window, schema, generation and target identity', async () => {
  const view = await launch();view.live();
  view.command('Biceps',1,undefined,'https://evil.example');view.command('Biceps',1,undefined,undefined,{});
  view.command('Biceps',0);view.command('Biceps',2);view.command('Biceps',1,{kind:'bot',bot:'Other'});
  view.command('Biceps',1,{kind:'bot',bot:'Biceps',account:8});
  view.command('Biceps',1,{kind:'player',source:12,target:22});
  view.command('Biceps',1,{kind:'player',source:11,target:11});
  assert.equal(view.sent.length,0);assert.equal(view.messages.at(-1).status,'live');
  view.command('Biceps',1,{kind:'player',source:11,target:22});view.command('Other',1);
  assert.equal(view.sent.length,1);assert.equal(view.sent[0].target.kind,'player');
});

test('rejected switches preserve the current view and surface the actual rejection', async () => {
  const view = await launch();view.live();view.command('Biceps',1);
  view.control({type:'rejected',bot:'Triceps',generation:0,requested:1,error:'Bot is no longer online'});
  assert.match(view.inspectStatus.textContent,/no longer online/);
  assert.equal(view.messages.at(-1).status,'live');assert.equal(view.messages.at(-1).bot,'Triceps');
  assert.ok(view.messages.some(message=>message.type==='openrotmg-bot-rejected' && message.requested===1));
  view.command('Other',1);assert.equal(view.sent.length,2);assert.deepEqual(view.counts(),{creates:1,loads:1});
});

test('an unavailable source remains switchable without reloading or accepting old native heartbeats', async () => {
  const view = await launch();view.live();view.control({type:'unavailable',bot:'Triceps',generation:0});
  view.live();view.advance(30000);assert.equal(view.messages.at(-1).status,'disconnected');
  view.command('Biceps',1);view.control({type:'selected',bot:'Biceps',generation:1});
  view.attached('Biceps',1,22,8);view.native('frame','22');view.native('tick','22');
  assert.equal(view.messages.at(-1).status,'live');assert.equal(view.messages.at(-1).bot,'Biceps');
  assert.deepEqual(view.counts(),{creates:1,loads:1});assert.equal(view.errors.length,0);
});

test('unacknowledged switches, mismatched replies and private control fields fail without reload', async () => {
  const timeout = await launch();timeout.live();timeout.command('Biceps',1);timeout.advance(8000);
  assert.equal(timeout.messages.at(-1).status,'error');assert.match(timeout.messages.at(-1).error,/8 seconds/);
  for (const reply of [{type:'selected',bot:'Other',generation:1},
    {type:'attached',bot:'Triceps',generation:0,player:11,character:7,account:8}]) {
    const view = await launch();view.live();view.command('Biceps',1);view.control(reply);
    assert.equal(view.messages.at(-1).status,'error');assert.deepEqual(view.counts(),{creates:1,loads:1});
    view.live();assert.equal(view.messages.at(-1).status,'error');
  }
});

test('native reconnect cannot reuse a previous attachment receipt or old actor heartbeat', async () => {
  const view = await launch();view.live();view.trace('openrotmg-spectator:connecting:');
  view.live();assert.equal(view.messages.at(-1).status,'connecting');
  view.attached('Triceps',0,33,9);view.live();assert.equal(view.messages.at(-1).status,'connecting');
  view.native('frame','33');view.native('tick','33');assert.equal(view.messages.at(-1).status,'live');
  view.events.pagehide();assert.deepEqual(view.counts(),{creates:1,loads:1});
});

test('invalid paths/names fail without loading arbitrary movies or sockets', async () => {
  for (const path of ['/api/bots/Triceps/view/extra', '/api/bots/%2f/view', '/api/bots/%ZZ/view', '/api/bots/../view']) {
    const view = await launch({path});
    assert.equal(view.options, undefined);
    assert.match(view.status.textContent, /^error:/);
  }
});
