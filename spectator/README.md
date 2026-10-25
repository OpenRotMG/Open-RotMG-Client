# Native spectator
`client.swf` stays immutable; `lock.json` pins the separately derived `spectator.swf` (only ABC1 changes).
Build the pinned RABCDAsm with `rabcdasm-determinism.patch`, then run `python3 scripts/build_spectator.py /path/to/RABCDAsm`; verify with `RABCDASM=/path/to/RABCDAsm python3 -m unittest discover -s tests` and `node --test tests/*.mjs`.
Serve the spectator movie **raw**, with `spectator.html/js`, the read-only `/api/bots/{name}/socket`, and same-origin vendor/sfx assets. Never rewrite it as the playable movie. Native draw/tick, travel/death, tooltips and input/privacy isolation require real-client verification; no renderer fallback exists.
