(async () => {
  const match = /^\/api\/bots\/([^/]+)\/view$/.exec(location.pathname);
  if (!match) throw new Error('Expected /api/bots/{name}/view');
  const bot = decodeURIComponent(match[1]);
  if (!/^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(bot)) throw new Error('Invalid bot name');
  const label = document.querySelector('#status');
  let state, failure, connectedAt = performance.now(), lastFrame = null, lastTick = null;
  const menu = document.querySelector('#perspective');
  const inspectStatus = document.querySelector('#inspect-status');
  const client = document.querySelector('#client');
  const profile = value => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(value);
  const actor = value => Number.isInteger(value) && value >= 0 && value <= 2147483647;
  let source = null, generation = 0, request, menuTimer, selected, lookups = [];
  const clearInspect = () => {
    generation++;
    request?.abort();
    request = null;
    window.clearTimeout(menuTimer);
    selected = null;
    menu.hidden = true;
    inspectStatus.textContent = '';
  };
  const lookupError = (error, current) => {
    if (current !== generation) return;
    inspectStatus.textContent = String(error.message || error);
    console.error(error);
  };
  const lookup = async (from, target, current) => {
    const now = performance.now();
    lookups = lookups.filter(time => now - time < 1000);
    if (lookups.length >= 4) throw new Error('Perspective lookup rate limited');
    lookups.push(now);
    const controller = new AbortController();
    request = controller;
    const timeout = window.setTimeout(() => controller.abort(), 3000);
    try {
      const response = await fetch(`/api/bots/${encodeURIComponent(bot)}/perspective/${target}?source=${from}`, {
        method: 'GET', mode: 'same-origin', credentials: 'omit', cache: 'no-store', redirect: 'error',
        referrerPolicy: 'no-referrer', signal: controller.signal
      });
      if (current !== generation) return null;
      if (controller.signal.aborted) throw new Error('Perspective lookup timed out');
      if (response.status === 404) return null;
      if (!response.ok) throw new Error(`Perspective lookup HTTP ${response.status}`);
      const body = await response.text();
      if (current !== generation) return null;
      if (controller.signal.aborted) throw new Error('Perspective lookup timed out');
      if (body.length > 1024) throw new Error('Oversized perspective lookup response');
      const result = JSON.parse(body);
      if (!result || Object.keys(result).sort().join(',') !== 'bot,player,source' ||
          !profile(result.bot) || result.player !== target || result.source !== from) {
        throw new Error('Invalid perspective lookup response');
      }
      return result;
    } catch (error) {
      if (controller.signal.aborted) throw new Error('Perspective lookup timed out');
      throw error;
    } finally {
      window.clearTimeout(timeout);
      if (request === controller) request = null;
    }
  };
  const inspect = async message => {
    clearInspect();
    const fields = /^openrotmg-spectator:inspect:(\d+):(\d+):(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/.exec(message);
    if (!fields) {console.warn('Malformed native spectator inspect trace'); return;}
    const [from, target, x, y] = fields.slice(1).map(Number);
    if (!actor(from) || !actor(target) || from !== source || from === target || x > 800 || y > 600 || state !== 'live') return;
    const current = generation;
    try {
      const result = await lookup(from, target, current);
      if (!result || current !== generation) return;
      selected = {target: result.bot, player: target, source: from, generation: current};
      menu.hidden = false;
      const rect = client.getBoundingClientRect();
      menu.style.left = `${Math.max(rect.left, Math.min(rect.left + x / 800 * rect.width, rect.right - menu.offsetWidth))}px`;
      menu.style.top = `${Math.max(rect.top, Math.min(rect.top + y / 600 * rect.height, rect.bottom - menu.offsetHeight))}px`;
      menuTimer = window.setTimeout(clearInspect, 5000);
    } catch (error) {lookupError(error, current);}
  };
  menu.querySelector('button').addEventListener('click', async () => {
    const choice = selected;
    const valid = choice && choice.source === source && choice.generation === generation && state === 'live';
    clearInspect();
    if (!valid) return;
    const current = generation;
    try {
      const result = await lookup(choice.source, choice.player, current);
      if (current !== generation) return;
      if (!result || result.bot !== choice.target) throw new Error('Perspective no longer available');
      window.parent.postMessage({type: 'openrotmg-bot-select', bot, target: choice.target}, '*');
    } catch (error) {lookupError(error, current);}
  });
  window.addEventListener('pointerdown', event => {if (!menu.contains(event.target)) clearInspect();}, true);
  window.addEventListener('keydown', event => {if (event.key === 'Escape') clearInspect();});
  window.addEventListener('resize', clearInspect);
  const publish = (status, error) => {
    if (state === status && failure === error) return;
    state = status;
    failure = error;
    if (status !== 'live') clearInspect();
    label.textContent = status === 'live' ? '' : `${status}${error ? `: ${error}` : ''}`;
    window.parent.postMessage({type: 'openrotmg-bot-view', bot, status, ...(error ? {error} : {})}, '*');
  };
  const fail = error => {
    publish('error', String(error.message || error));
    console.error(error);
  };
  window.addEventListener('error', event => fail(event.error || new Error(event.message)));
  window.addEventListener('unhandledrejection', event => fail(event.reason));
  publish('connecting');
  // Packet arrival alone is not rendering: require a completed native draw and a recent tick.
  const refresh = () => {
    if (state === 'error' || state === 'disconnected') return;
    const now = performance.now();
    if (lastFrame !== null && lastTick !== null) {
      publish(now - lastFrame < 5000 && now - lastTick < 5000 ? 'live' : 'stale');
    } else if (now - connectedAt >= 15000) {
      fail(new Error('Native view did not draw a bot and receive a tick within 15 seconds'));
    }
  };
  const nativeStatus = (status, error) => {
    if (status === 'connecting') {
      clearInspect();
      source = null;
      connectedAt = performance.now();
      lastFrame = lastTick = null;
      publish('connecting');
    } else if (status === 'frame' || status === 'tick') {
      if (status === 'frame') lastFrame = performance.now();
      else lastTick = performance.now();
      refresh();
    } else if (status === 'disconnected') publish('disconnected');
    else if (status === 'error') fail(new Error(error || 'Native client failed'));
    else fail(new Error(`Unknown native spectator status: ${status}`));
  };
  let lastHeartbeat = performance.now();
  const interval = window.setInterval(() => {
    refresh();
    if (performance.now() - lastHeartbeat >= 5000 && state) {
      window.parent.postMessage({type: 'openrotmg-bot-view', bot, status: state, ...(failure ? {error: failure} : {})}, '*');
      lastHeartbeat = performance.now();
    }
  }, 1000);
  window.addEventListener('pagehide', () => {clearInspect(); window.clearInterval(interval);}, {once: true});
  try {
    if (!window.RufflePlayer) throw new Error('Ruffle assets unavailable');
    const player = window.RufflePlayer.newest().createPlayer();
    client.append(player);
    const socket = new URL(`/api/bots/${encodeURIComponent(bot)}/socket`, location.href);
    socket.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket.searchParams.set('cursor', '1');
    await player.ruffle().load({
      url: '/api/bots/client.swf?v=02ce5f05395aac9283688f3b6a64a907ca654f6d076353f89036bb14a00c10d9', parameters: {bot},
      contextMenu: 'off',
      autoplay: 'on', unmuteOverlay: 'hidden', preferredRenderer: 'wgpu-webgl',
      logLevel: 'warn', openUrlMode: 'deny', allowScriptAccess: false,
      socketProxy: [{host: '127.0.0.1', port: 2050, proxyUrl: socket.href}],
      urlRewriteRules: [
        [/^https?:\/\/realmofthemadgod\.appspot\.com\/sfx\//, new URL('/sfx/', location.href).href],
        [/^https?:\/\/realmofthemadgod\.appspot\.com\/music\//, new URL('/sfx/music/', location.href).href]
      ]
    });
    player.ruffle().traceObserver = message => {
      if (message.startsWith('openrotmg-spectator:cursor:')) {console.debug(message); return;}
      if (message.startsWith('openrotmg-spectator:inspect:')) {void inspect(message); return;}
      if (message.startsWith('openrotmg-spectator:source:')) {
        const value = /^openrotmg-spectator:source:(-?\d+)$/.exec(message);
        const next = value ? Number(value[1]) : NaN;
        if (!actor(next) && next !== -1) {clearInspect(); source = null; console.warn('Malformed native spectator source trace'); return;}
        if (source !== next) clearInspect();
        source = next === -1 ? null : next;
        return;
      }
      const status = /^openrotmg-spectator:([a-z]+):(.*)$/s.exec(message);
      if (status) nativeStatus(status[1], status[2]);
    };
  } catch (error) {
    fail(error);
  }
})().catch(error => {
  document.querySelector('#status').textContent = `error: ${error.message}`;
  console.error(error);
});
