import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const script = await readFile(new URL('../launcher.js', import.meta.url), 'utf8');
for (const [page, mode, movie] of [['index.html', 'game', '/client.swf'], ['draw.html', 'editor', '/native-texture-editor.swf']]) {
  test(`${page} explicitly loads ${movie} through the shared protected launcher`, async () => {
    const html = await readFile(new URL(`../${page}`, import.meta.url), 'utf8');
    assert.ok(html.includes(`data-mode="${mode}"`));
    assert.ok(html.includes('<script src="launcher.js"></script>'));
    const gameplay = await readFile(new URL('../index.html', import.meta.url), 'utf8');
    assert.equal(html.match(/content="default-src[^"]+"/)[0], gameplay.match(/content="default-src[^"]+"/)[0]);
    let options;
    const player = {addEventListener() {}, ruffle: () => ({load: async value => {options = value;}})};
    const nodes = {'#client': {dataset: {mode}, append() {}}, '#status': {}};
    await vm.runInNewContext(script, {window: {addEventListener() {}, RufflePlayer: {newest: () => ({createPlayer: () => player})}},
      document: {querySelector: key => nodes[key]}, URL, location: {href: `http://127.0.0.1:18923/${page}?url=https://evil.example/a.swf`}});
    assert.equal(options.url, movie);
    assert.equal(options.contextMenu, mode === 'game' ? 'off' : 'on');
    assert.equal(options.allowScriptAccess, false);
    assert.equal(options.openUrlMode, 'deny');
    assert.equal(options.socketProxy[0].proxyUrl, 'ws://127.0.0.1:18923/game');
    assert.equal(options.urlRewriteRules[0][1], 'http://127.0.0.1:18923/legacy-api/');
    assert.equal(options.urlRewriteRules[1][1], 'http://127.0.0.1:18923/sfx/');
    const rewrite = url => options.urlRewriteRules.reduce((value, [pattern, replacement]) => value.replace(pattern, replacement), url);
    for (const protocol of ['http', 'https']) {
      for (const family of ['char/list', 'account/verify', 'fame/list', 'guild/listMembers', 'picture/save', 'picture/list', 'picture/get', 'picture/delete']) {
        assert.equal(rewrite(`${protocol}://127.0.0.1:8080/${family}`), `http://127.0.0.1:18923/legacy-api/${family}`);
      }
    }
    for (const path of ['/client.swf', '/native-texture-editor.swf', '/vendor/ruffle.js', '/draw.html', '/game']) {
      assert.equal(rewrite('http://127.0.0.1:8080' + path), 'http://127.0.0.1:8080' + path);
    }
    for (const url of ['http://localhost:8080/picture/get', 'http://127.0.0.1:8081/picture/get',
      'https://127.0.0.1.evil.example:8080/picture/get', 'http://127.0.0.1:8080@evil.example/picture/get',
      'http://127.0.0.1:8080/pictures/get', 'http://127.0.0.1:8080/picture',
      'ftp://127.0.0.1:8080/picture/get', 'http://127.0.0.1:8080/?next=/picture/get']) assert.equal(rewrite(url), url);
  });
}
test('missing, arbitrary and URL-like modes fail explicitly without loading any movie', async () => {
  for (const mode of [undefined, '', 'https://evil.example/movie.swf', '../client.swf']) {
    let loads = 0;
    const player = {addEventListener() {}, ruffle: () => ({load: async () => {loads++;}})};
    const nodes = {'#client': {dataset: {mode}, append() {}}, '#status': {}};
    await vm.runInNewContext(script, {window: {addEventListener() {}, RufflePlayer: {newest: () => ({createPlayer: () => player})}},
      document: {querySelector: key => nodes[key]}, URL, location: {href: 'https://example.test/'}, console: {error() {}}});
    assert.equal(loads, 0);
    assert.match(nodes['#status'].textContent, /Unknown client mode/);
  }
});
