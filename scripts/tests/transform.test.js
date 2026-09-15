// Run with: node --test scripts/tests/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const transformCode = fs.readFileSync(path.join(__dirname, '../../plugin/transform.js'), 'utf-8');

const CATALOG_URL = 'https://raw.githubusercontent.com/ExcuseMi/trmnl-comic-library-plugin/refs/heads/main/data/comic_urls.json';

function rssFor(url) {
  return `<rss><channel><title>${url}</title><item><title>Strip</title>` +
    `<link>${url}/1</link><description><![CDATA[<img src="${url}/strip.png">]]></description>` +
    `</item></channel></rss>`;
}

// Loads transform.js into a sandbox whose fetch serves a fake feed for any URL
// and records every requested URL, so tests never hit the network.
function loadTransform() {
  const fetched = [];
  const sandbox = {
    AbortController, setTimeout, clearTimeout, console,
    fetch: async (url) => {
      fetched.push(url);
      if (url === CATALOG_URL) {
        return { ok: true, json: async () => ['https://example.com/catalog-a', 'https://example.com/catalog-b'] };
      }
      return { ok: true, text: async () => rssFor(url) };
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(transformCode, sandbox);
  return { sandbox, fetched };
}

function inputWith(customFields) {
  return { trmnl: { plugin_settings: { custom_fields_values: customFields } } };
}

test('parseMultiSelect accepts arrays, JSON strings and comma strings', () => {
  const { sandbox } = loadTransform();
  const parse = (v) => JSON.parse(JSON.stringify(sandbox.parseMultiSelect(v)));

  assert.deepEqual(parse(['https://a', '', 'https://b']), ['https://a', 'https://b']);
  assert.deepEqual(parse('["https://a","https://b"]'), ['https://a', 'https://b']);
  assert.deepEqual(parse('https://a, https://b'), ['https://a', 'https://b']);
  assert.deepEqual(parse(''), []);
  assert.deepEqual(parse(undefined), []);
});

test('run() only fetches the selected comic when comics is an array', async () => {
  const { sandbox, fetched } = loadTransform();
  const selected = 'https://comiccaster.xyz/rss/tbd-toons-by-dan';

  const result = await sandbox.run(inputWith({ comics: [selected], only_show_latest: 'true', extra_rss_feeds: '' }));

  assert.deepEqual([...fetched], [selected]);
  assert.equal(result.comics.length, 1);
  assert.equal(result.comics[0].source, selected);
});

test('run() merges all selection fields and extra feeds', async () => {
  const { sandbox, fetched } = loadTransform();

  await sandbox.run(inputWith({
    comics: ['https://example.com/a'],
    comics_other_languages: ['https://example.com/b'],
    comics_political: '["https://example.com/c"]',
    extra_rss_feeds: 'https://example.com/d, https://example.com/a'
  }));

  assert.deepEqual([...fetched].sort(), ['https://example.com/a', 'https://example.com/b', 'https://example.com/c', 'https://example.com/d']);
});

test('run() falls back to the full catalog only when nothing is selected', async () => {
  const { sandbox, fetched } = loadTransform();

  await sandbox.run(inputWith({ comics: [], extra_rss_feeds: '' }));

  assert.equal(fetched[0], CATALOG_URL);
  assert.deepEqual(fetched.slice(1).sort(), ['https://example.com/catalog-a', 'https://example.com/catalog-b']);
});
