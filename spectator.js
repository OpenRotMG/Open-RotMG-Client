(async () => {
  const match = /^\/api\/bots\/([^/]+)\/view$/.exec(location.pathname);
  if (!match) throw new Error('Expected /api/bots/{name}/view');
  const bot = decodeURIComponent(match[1]);
  if (!/^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(bot)) throw new Error('Invalid bot name');
  const label = document.querySelector('#status');
  let state, failure, connectedAt = performance.now(), lastFrame = null, lastTick = null;
  const publish = (status, error) => {
    if (state === status && failure === error) return;
    state = status;
    failure = error;
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
  const interval = window.setInterval(refresh, 1000);
  window.addEventListener('pagehide', () => window.clearInterval(interval), {once: true});
  try {
    if (!window.RufflePlayer) throw new Error('Ruffle assets unavailable');
    const player = window.RufflePlayer.newest().createPlayer();
    document.querySelector('#client').append(player);
    const socket = new URL(`/api/bots/${encodeURIComponent(bot)}/socket`, location.href);
    socket.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    await player.ruffle().load({
      url: '/api/bots/client.swf', parameters: {bot},
      autoplay: 'on', unmuteOverlay: 'hidden', preferredRenderer: 'wgpu-webgl',
      logLevel: 'warn', openUrlMode: 'deny', allowScriptAccess: false,
      socketProxy: [{host: '127.0.0.1', port: 2050, proxyUrl: socket.href}],
      urlRewriteRules: [[/^https?:\/\/realmofthemadgod\.appspot\.com\/sfx\//, new URL('/sfx/', location.href).href]]
    });
    player.ruffle().traceObserver = message => {
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
