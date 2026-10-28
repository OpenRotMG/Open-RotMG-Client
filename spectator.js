(async () => {
  const match = /^\/api\/bots\/([^/]+)\/view$/.exec(location.pathname);
  if (!match) throw new Error('Expected /api/bots/{name}/view');
  let bot = decodeURIComponent(match[1]);
  if (!/^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(bot)) throw new Error('Invalid bot name');
  const label = document.querySelector('#status');
  const initializingAt = performance.now();
  let state, failure, connectedAt = null, lastFrame = null, lastTick = null;
  const menu = document.querySelector('#perspective');
  const button = menu.querySelector('button');
  const inspectStatus = document.querySelector('#inspect-status');
  const client = document.querySelector('#client');
  const profile = value => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(value);
  const actor = value => Number.isInteger(value) && value >= 0 && value <= 2147483647;
  let source = null, generation = 0, request, menuTimer, selected, lookups = [];
  let control, parentOrigin = null, watchGeneration = 0, bound = null, pending = null, leaving = false, loaded = false;
  const version = value => Number.isInteger(value) && value >= 0 && value <= 4294967295;
  const shape = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join(',') === keys;
  const post = message => window.parent.postMessage(message, parentOrigin);
  const announce = () => {
    const message = {bot, status: state, ...(failure ? {error: failure} : {})};
    // Already-open site pages still consume the legacy public status during the rollout.
    window.parent.postMessage({type: 'openrotmg-bot-view', ...message}, '*');
    if (parentOrigin !== null) post({type: 'openrotmg-bot-state', generation: watchGeneration, ...message});
  };
  const clearInspect = () => {
    generation++;
    request?.abort();
    request = null;
    window.clearTimeout(menuTimer);
    selected = null;
    menu.hidden = true;
    button.disabled = false;
    button.textContent = 'View perspective';
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
      if (current !== generation) return;
      selected = result ? {target: result.bot, player: target, source: from, generation: current} : null;
      button.disabled = !result;
      button.textContent = result ? 'View perspective' : 'Player (cannot spy)';
      menu.hidden = false;
      const rect = client.getBoundingClientRect();
      menu.style.left = `${Math.max(rect.left, Math.min(rect.left + x / 800 * rect.width, rect.right - menu.offsetWidth))}px`;
      menu.style.top = `${Math.max(rect.top, Math.min(rect.top + y / 600 * rect.height, rect.bottom - menu.offsetHeight))}px`;
      menuTimer = window.setTimeout(clearInspect, 5000);
    } catch (error) {lookupError(error, current);}
  };
  button.addEventListener('click', async () => {
    const choice = selected;
    const valid = choice && choice.source === source && choice.generation === generation && state === 'live';
    clearInspect();
    if (!valid) return;
    const current = generation;
    try {
      const result = await lookup(choice.source, choice.player, current);
      if (current !== generation) return;
      if (!result || result.bot !== choice.target) throw new Error('Perspective no longer available');
      const target = {kind: 'player', source: choice.source, target: choice.player};
      if (window.parent === window) switchView({bot: choice.target, generation: watchGeneration + 1, target});
      else {
        window.parent.postMessage({type: 'openrotmg-bot-select', bot, target: choice.target}, '*');
        post({type: 'openrotmg-bot-choice', bot, generation: watchGeneration,
          target: choice.target, source: choice.source, player: choice.player});
      }
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
    announce();
  };
  const fail = error => {
    publish('error', String(error.message || error));
    control?.close(1000, 'Viewer failed');
    console.error(error);
  };
  window.addEventListener('error', event => fail(event.error || new Error(event.message)));
  window.addEventListener('unhandledrejection', event => fail(event.reason));
  publish('connecting');
  // Packet arrival alone is not rendering: require a completed native draw and a recent tick.
  const refresh = () => {
    if (state === 'error') return;
    const now = performance.now();
    if (!loaded) {
      if (now - initializingAt >= 60000) fail(new Error('Native renderer did not initialize within 60 seconds'));
      return;
    }
    if (pending) {
      if (now - pending.at >= 8000) fail(new Error('Perspective switch was not acknowledged within 8 seconds'));
      return;
    }
    if (state === 'disconnected') return;
    if (lastFrame !== null && lastTick !== null) {
      publish(now - lastFrame < 5000 && now - lastTick < 5000 ? 'live' : 'stale');
    } else if (now - connectedAt >= 15000) {
      fail(new Error('Native view did not draw a bot and receive a tick within 15 seconds'));
    }
  };
  const nativeStatus = (status, error) => {
    if (status === 'connecting') {
      clearInspect();
      source = bound = null;
      connectedAt = loaded ? performance.now() : null;
      lastFrame = lastTick = null;
      publish('connecting');
    } else if (status === 'frame' || status === 'tick') {
      const player = /^\d+$/.test(error) ? Number(error) : NaN;
      if (pending || !bound || !actor(player) || player <= 0 || player !== bound.player) return;
      if (status === 'frame') {
        if (source !== player) clearInspect();
        source = player;
        lastFrame = performance.now();
      }
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
      announce();
      lastHeartbeat = performance.now();
    }
  }, 1000);
  window.addEventListener('pagehide', () => {
    leaving = true;clearInspect();window.clearInterval(interval);control?.close(1000, 'Viewer closed');
  }, {once: true});
  const switchView = message => {
    const target = message.target;
    if (!profile(message.bot) || !version(message.generation) || message.generation !== watchGeneration + 1 || pending) return;
    if (!(shape(target, 'bot,kind') && target.kind === 'bot' && target.bot === message.bot ||
        shape(target, 'kind,source,target') && target.kind === 'player' && bound &&
        target.source === source && source === bound.player && actor(target.target) && target.target > 0 && target.target !== source)) {
      const error = 'Perspective source or target changed; inspect again';
      post({type: 'openrotmg-bot-rejected', bot, generation: watchGeneration, requested: message.generation, error});
      lookupError(new Error(error), generation);announce();return;
    }
    if (state === 'error' || control?.readyState !== WebSocket.OPEN) throw new Error('Viewer control is not available');
    if (message.bot === bot) return;
    pending = {bot: message.bot, generation: message.generation, at: loaded ? performance.now() : null};
    publish('connecting');
    control.send(JSON.stringify({generation: message.generation, target}));
  };
  window.addEventListener('message', event => {
    if (parentOrigin === null || event.origin !== parentOrigin || event.source !== window.parent ||
        !shape(event.data, 'bot,generation,target,type') || event.data.type !== 'openrotmg-bot-watch') return;
    try {switchView(event.data);} catch (error) {fail(error);}
  });
  const openControl = () => new Promise((resolve, reject) => {
    const url = new URL(`/api/bots/${encodeURIComponent(bot)}/control`, location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    let ready = false;
    const timer = window.setTimeout(() => reject(new Error('Viewer control did not initialize within 5 seconds')), 5000);
    control = new WebSocket(url.href);
    const failed = error => {
      window.clearTimeout(timer);
      if (ready) fail(error); else reject(error);
    };
    control.onerror = () => failed(new Error('Viewer control connection failed'));
    control.onclose = event => {
      if (!leaving && state !== 'error') failed(new Error(`Viewer control closed: ${event.reason || event.code}`));
    };
    control.onmessage = event => {
      if (leaving || state === 'error') return;
      try {
        if (typeof event.data !== 'string' || event.data.length > 512) throw new Error('Invalid viewer control frame');
        const data = JSON.parse(event.data);
        if (!ready) {
          if (!shape(data, 'bot,generation,parent_origin,type,view') || data.type !== 'ready' || data.bot !== bot || data.generation !== 0 ||
              typeof data.view !== 'string' || !/^[a-f0-9]{32}$/.test(data.view) || typeof data.parent_origin !== 'string' ||
              !['http:', 'https:'].includes(new URL(data.parent_origin).protocol) ||
              new URL(data.parent_origin).origin !== data.parent_origin) throw new Error('Invalid viewer control initialization');
          parentOrigin = window.parent === window ? new URL(location.href).origin : data.parent_origin;
          ready = true;window.clearTimeout(timer);
          post({type: 'openrotmg-bot-ready', bot, generation: 0});announce();resolve(data.view);
        } else if (shape(data, 'bot,generation,type') && data.type === 'selected' && profile(data.bot) && version(data.generation)) {
          if (!pending || data.generation !== pending.generation || data.bot !== pending.bot) throw new Error('Unexpected perspective selection');
          bot = data.bot;watchGeneration = data.generation;pending = bound = source = null;
          lastFrame = lastTick = null;connectedAt = loaded ? performance.now() : null;state = undefined;
          post({type: 'openrotmg-bot-selected', bot, generation: watchGeneration});publish('connecting');
        } else if (shape(data, 'bot,generation,type') && data.type === 'unavailable' && profile(data.bot) && version(data.generation)) {
          if (data.generation !== watchGeneration || data.bot !== bot) return;
          bound = source = lastFrame = lastTick = null;
          publish('disconnected', 'Bot is offline or has no living character');
        } else if (shape(data, 'bot,character,generation,player,type') && data.type === 'attached' &&
            profile(data.bot) && version(data.generation) && actor(data.player) && data.player > 0 && actor(data.character) && data.character > 0) {
          if (data.generation !== watchGeneration || data.bot !== bot) return;
          bound = {player: data.player, character: data.character};source = null;
          lastFrame = lastTick = null;
          if (loaded && (connectedAt === null || state === 'disconnected')) connectedAt = performance.now();
          publish('connecting');
        } else if (shape(data, 'bot,error,generation,requested,type') && data.type === 'rejected' && data.bot === bot &&
            data.generation === watchGeneration && pending && data.requested === pending.generation && typeof data.error === 'string' && data.error.trim()) {
          pending = null;post({type: 'openrotmg-bot-rejected', bot, generation: watchGeneration, requested: data.requested, error: data.error});
          lookupError(new Error(data.error), generation);refresh();
        } else throw new Error('Invalid viewer control message');
      } catch (error) {failed(error);}
    };
  });
  try {
    if (!window.RufflePlayer) throw new Error('Ruffle assets unavailable');
    const view = await openControl();
    const player = window.RufflePlayer.newest().createPlayer();
    client.append(player);
    const socket = new URL(`/api/bots/views/${view}/socket`, location.href);
    socket.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket.searchParams.set('cursor', '2');
    await player.ruffle().load({
      url: '/api/bots/client.swf?v=06ba9e7f31be9c4b3b408d36000b1889cda03d68aecf11dbb83cc2a4b48cfed0', parameters: {bot},
      contextMenu: 'off',
      autoplay: 'on', unmuteOverlay: 'hidden', preferredRenderer: 'wgpu-webgl',
      logLevel: 'warn', openUrlMode: 'deny', allowScriptAccess: false,
      socketProxy: [{host: '127.0.0.1', port: 2050, proxyUrl: socket.href}],
      urlRewriteRules: [
        [/^https?:\/\/realmofthemadgod\.appspot\.com\/sfx\//, new URL('/sfx/', location.href).href],
        [/^https?:\/\/realmofthemadgod\.appspot\.com\/music\//, new URL('/sfx/music/', location.href).href]
      ]
    });
    if (performance.now() - initializingAt >= 60000) throw new Error('Native renderer did not initialize within 60 seconds');
    // Cold WASM/GPU startup is not a native connection attempt; its own bounded deadline remains above.
    loaded = true;
    if (pending?.at === null) pending.at = performance.now();
    connectedAt ??= performance.now();
    player.ruffle().traceObserver = message => {
      if (message.startsWith('openrotmg-spectator:cursor:') || message.startsWith('openrotmg-spectator:compose:')) {console.debug(message); return;}
      if (message.startsWith('openrotmg-spectator:inspect:')) {void inspect(message); return;}
      if (message.startsWith('openrotmg-spectator:source:')) {
        const value = /^openrotmg-spectator:source:(-?\d+)$/.exec(message);
        const next = value ? Number(value[1]) : NaN;
        if (!actor(next) && next !== -1) {clearInspect(); source = null; console.warn('Malformed native spectator source trace'); return;}
        if (source !== next) clearInspect();
        if (next !== bound?.player) {
          source = lastFrame = lastTick = null;
          if (state !== 'error' && state !== 'disconnected') publish('connecting');
        } else source = next;
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
