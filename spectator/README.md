# Read-only native 123.5.1 spectator

`client.swf` is immutable. `spectator.swf` is its separately derived, compressed movie; `lock.json` pins both. Only ABC block 1 changes. `scripts/build_spectator.py` contains the complete method transforms, not a copy of extracted client sources.

Build RABCDAsm at the commit in `lock.json` with `rabcdasm-determinism.patch` applied (`git apply`, then `rdmd build_rabcdasm.d`). The patch removes hash-table iteration order from pool ordering. D compiler, zlib or assembler differences must not silently replace the pinned artifact: verify the output checksum.

```sh
python3 scripts/build_spectator.py /path/to/RABCDAsm
RABCDASM=/path/to/RABCDAsm python3 -m unittest discover -s tests
node --test tests/*.mjs
```

Serve `spectator.html` at `/api/bots/{name}/view`, `spectator.js` at `/api/bots/spectator.js`, and **spectator.swf** at `/api/bots/client.swf`. Existing same-origin `/vendor/` and `/sfx/` assets are required. The socket proxy is `/api/bots/{name}/socket`. CWS must be decompressed before any backend binary endpoint rewrites.

Bootstrap directly constructs native GameSprite, using only public HUD metadata and dummy HELLO/LOAD initialization. RECONNECT re-enters that native bootstrap, never account/menu/Play. Self movement uses remote interpolation. Stage action capture precedes HUD predictions; hover events remain available. The socket boundary additionally permits only HELLO, LOAD, PONG, UPDATEACK, SHOOTACK and GOTOACK. The backend must independently reject gameplay input.

Status uses Ruffle's `traceObserver` with a reserved prefix, not ExternalInterface/eval; script access stays disabled. `live` means a completed native draw plus a recent native tick, not telemetry or asset-load success; it is not proof of GPU presentation. Native integration must still inspect rendering, tooltips, input isolation, world travel and committed death/replacement. No renderer fallback exists.
