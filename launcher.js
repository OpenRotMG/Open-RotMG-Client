(async () => {
  const player = window.RufflePlayer.newest().createPlayer();
  document.querySelector('#client').append(player);
  const heldKeys = new Map();
  player.addEventListener('keydown', event => heldKeys.set(event.code, event));
  player.addEventListener('keyup', event => heldKeys.delete(event.code));
  const releaseKeys = () => {
    const keys = [...heldKeys.values()];
    heldKeys.clear();
    for (const event of keys) window.dispatchEvent(new KeyboardEvent('keyup', event));
  };
  // Ruffle ignores key-up after losing focus, so release before its focusout handler runs.
  player.addEventListener('focusout', event => {
    if (!player.contains(event.relatedTarget)) releaseKeys();
  }, true);
  window.addEventListener('blur', releaseKeys);
  const accountEndpoint = new URL('/legacy-api/', location.href).href;
  const audioEndpoint = new URL('/sfx/', location.href).href;
  const socketEndpoint = new URL('/game', location.href);
  socketEndpoint.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const movies = {game: '/client.swf', editor: '/native-texture-editor.swf'};
  const mode = document.querySelector('#client').dataset.mode;
  if (!Object.hasOwn(movies, mode)) throw new Error(`Unknown client mode: ${mode}`);
  await player.ruffle().load({
    url: movies[mode],
    // Game input should not open emulator controls: https://github.com/ruffle-rs/ruffle/blob/89a7049965f3090e706265670df309a5128233ac/web/packages/core/src/public/config/load-options.ts#L160-L176
    contextMenu:mode === 'game' ? 'off' : 'on',
    autoplay:'on',unmuteOverlay:'hidden',preferredRenderer:'wgpu-webgl',
    // Get Gold uses navigateToURL; require consent instead of silently denying it: https://github.com/ruffle-rs/ruffle/blob/89a7049965f3090e706265670df309a5128233ac/web/src/navigator.rs
    logLevel:'info',openUrlMode:mode === 'game' ? 'confirm' : 'deny',allowScriptAccess:false,
    socketProxy:[{host:'127.0.0.1',port:2050,proxyUrl:socketEndpoint.href}],
    urlRewriteRules:[
      [/^https?:\/\/127\.0\.0\.1:8080\/(?=(?:char|account|fame|guild|picture)\/)/,accountEndpoint],
      [/^https?:\/\/realmofthemadgod\.appspot\.com\/sfx\//,audioEndpoint]
    ]
  });
  document.querySelector('#status').textContent = '';
})().catch(error => {
  document.querySelector('#status').textContent = String(error);
  console.error(error);
});
