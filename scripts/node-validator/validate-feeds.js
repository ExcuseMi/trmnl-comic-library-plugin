'use strict';

const fs = require('fs');
const vm = require('vm');

// ---------------------------------------------------------------------------
// Load transform.js from the same directory (copied in at Docker build time).
// This is the serverless run()-based rewrite — no fast-xml-parser dependency.
// PARSER_CONFIG is inlined in the file itself now (see src/transform.js), so
// there's no separate comic_parser_data.json to load here anymore.
// ---------------------------------------------------------------------------
const transformCode = fs.readFileSync(__dirname + '/transform.js', 'utf-8');

function makeSandbox() {
  // Real Date constructor from the outer scope
  const RealDate = Date;

  // Sandbox with a Date subclass that:
  // - acts as a real Date constructor
  // - overrides Date.now() to always return 0 (deterministic item selection
  //   in processFeed's "pick a random item" branch)
  const sandbox = {
    Date: class extends RealDate {
      constructor(...args) {
        super(...args);
      }
      static now() { return 0; }
    },
    Array,
    Object,
    String,
    Number,
    Boolean,
    RegExp,
    Math,
    JSON,
    parseInt,
    parseFloat,
    isNaN,
    isFinite,
    undefined,
  };
  vm.createContext(sandbox);
  // Defines parseFeedXml, processFeed, isFeed, PARSER_CONFIG, run, etc. as
  // sandbox globals. Doesn't execute any fetch — those only run if run()
  // itself is invoked, which this validator deliberately doesn't do (it wants
  // per-feed diagnostics, not the batch/retry behavior run() is designed for).
  vm.runInContext(transformCode, sandbox);
  return sandbox;
}

/**
 * Parses raw feed XML using the plugin's own hand-rolled parser (not
 * fast-xml-parser) — this is the actual regression test: does our parser
 * produce a shape processFeed() can still work with, across every real feed?
 */
function parseWithPluginParser(sandbox, xml) {
  return vm.runInContext('parseFeedXml(' + JSON.stringify(xml) + ')', sandbox);
}

function runTransform(sandbox, parsedXml) {
  const input = JSON.stringify(parsedXml);
  return vm.runInContext(`processFeed(${input}, PARSER_CONFIG, {})`, sandbox);
}

// One shared sandbox for the whole run — transform.js has no per-call state,
// and Date.now() is deterministically stubbed anyway, so this is safe to reuse
// across concurrent validateFeed() calls instead of rebuilding a VM context per feed.
const SANDBOX = makeSandbox();

// ---------------------------------------------------------------------------
// Promo / generic-content detection (ported from Python validator)
// ---------------------------------------------------------------------------
function isGenericPromoRss(item) {
  const link = item.link || '';
  const lastSegment = String(link).split('/').pop();
  const linkHasDate = /\d/.test(lastSegment);

  if (!linkHasDate) {
    const description = item.description || item.encoded || '';
    const descLower = String(description).toLowerCase();
    const imgMatch = descLower.match(/src="([^"]+)"/);
    if (imgMatch) {
      const urlLower = imgMatch[1].toLowerCase();
      if (urlLower.includes('generic_fb') || urlLower.includes('social_fb_generic')) return true;
      if (urlLower.includes('gocomicscmsassets')) return true;
    }
    if (descLower.includes('explore the archive') && descLower.includes('read extra content')) return true;
  }
  return false;
}

function isGenericPromoAtom(entry) {
  let linkHref = '';
  if (entry.link) {
    linkHref = typeof entry.link === 'string' ? entry.link : (entry.link.href || '');
  }
  const lastSegment = String(linkHref).split('/').pop();
  const linkHasDate = /\d/.test(lastSegment);

  if (!linkHasDate) {
    let summaryText = '';
    if (entry.summary) {
      summaryText = typeof entry.summary === 'string' ? entry.summary : (entry.summary.__content__ || '');
    }
    if (!summaryText && entry.content) {
      summaryText = typeof entry.content === 'string' ? entry.content : (entry.content.__content__ || '');
    }
    const lower = summaryText.toLowerCase();
    const imgMatch = lower.match(/src="([^"]+)"/);
    if (imgMatch) {
      const urlLower = imgMatch[1].toLowerCase();
      if (urlLower.includes('generic_fb') || urlLower.includes('social_fb_generic')) return true;
      if (urlLower.includes('gocomicscmsassets')) return true;
    }
    if (lower.includes('explore the archive') && lower.includes('read extra content')) return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Image accessibility check (hotlink protection)
// ---------------------------------------------------------------------------
async function testImageAccess(imageUrl, feedUrl, timeout) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.min(timeout, 5000));

    const resp = await fetch(imageUrl, {
      method: 'HEAD',
      headers: { Referer: feedUrl, 'User-Agent': 'Mozilla/5.0 (compatible; ComicRSSValidator/1.0)' },
      redirect: 'follow',
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (resp.status === 403) return false;

    if (resp.status >= 400) {
      // Retry with GET (some servers block HEAD)
      const controller2 = new AbortController();
      const timer2 = setTimeout(() => controller2.abort(), Math.min(timeout, 5000));
      const resp2 = await fetch(imageUrl, {
        method: 'GET',
        headers: { Referer: feedUrl, 'User-Agent': 'Mozilla/5.0 (compatible; ComicRSSValidator/1.0)' },
        redirect: 'follow',
        signal: controller2.signal,
      });
      clearTimeout(timer2);
      // Consume body to prevent memory leak
      try { await resp2.arrayBuffer(); } catch {}
      if (resp2.status === 403 || resp2.status >= 400) return false;
    }
    return true;
  } catch {
    // Network errors — assume accessible (same as Python)
    return true;
  }
}

// ---------------------------------------------------------------------------
// Determine image_source from the transform result
// ---------------------------------------------------------------------------
function detectImageSource(parsedXml, imageUrl) {
  if (!imageUrl) return null;

  // Check if it came from an enclosure
  const items = parsedXml.rss?.channel?.item || parsedXml.feed?.entry;
  const firstItem = Array.isArray(items) ? items[0] : items;
  if (firstItem?.enclosure?.url === imageUrl) return 'enclosure';

  // Otherwise it came from description/summary/content
  if (parsedXml.feed) return 'summary';
  return 'description';
}

// ---------------------------------------------------------------------------
// Determine feed_type from parsed XML
// ---------------------------------------------------------------------------
function detectFeedType(parsedXml) {
  if (parsedXml.rss) return 'rss';
  if (parsedXml.feed) return 'atom';
  return null;
}

// ---------------------------------------------------------------------------
// Extract link from transform result context
// ---------------------------------------------------------------------------
function extractLink(parsedXml) {
  const isAtom = !!parsedXml.feed;
  const items = isAtom
    ? parsedXml.feed?.entry
    : parsedXml.rss?.channel?.item;
  const first = Array.isArray(items) ? items[0] : items;
  if (!first) return null;

  if (isAtom) {
    if (!first.link) return null;
    return typeof first.link === 'string' ? first.link : (first.link.href || null);
  }
  return first.link || null;
}

// ---------------------------------------------------------------------------
// Validate a single feed
// ---------------------------------------------------------------------------
async function validateFeed(name, url, timeout) {
  const result = {
    url,
    name,
    is_valid: false,
    error_message: null,
    comic_title: null,
    image_url: null,
    image_source: null,
    feed_type: null,
    link: null,
    caption: null,
  };

  try {
    // 1. Fetch XML
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; ComicRSSValidator/1.0)' },
      signal: controller.signal,
      redirect: 'follow',
    });
    clearTimeout(timer);

    if (!resp.ok) {
      result.error_message = `HTTP ${resp.status}`;
      return result;
    }

    const xml = await resp.text();

    // 2. Parse XML → JSON, using the plugin's own hand-rolled parser
    let parsed;
    try {
      parsed = parseWithPluginParser(SANDBOX, xml);
    } catch (e) {
      result.error_message = `XML parsing failed: ${e.message}`;
      return result;
    }

    if (!parsed) {
      result.error_message = 'Unknown feed type';
      return result;
    }

    result.feed_type = detectFeedType(parsed);

    if (!result.feed_type) {
      result.error_message = 'Unknown feed type';
      return result;
    }

    // 3. Check for generic promo content
    const isAtom = result.feed_type === 'atom';
    const items = isAtom ? parsed.feed?.entry : parsed.rss?.channel?.item;
    const firstItem = Array.isArray(items) ? items[0] : items;

    if (!firstItem) {
      result.error_message = 'No items/entries found in feed';
      return result;
    }

    if (isAtom ? isGenericPromoAtom(firstItem) : isGenericPromoRss(firstItem)) {
      result.error_message = 'Feed contains only generic promotional content';
      return result;
    }

    // 4. Run processFeed() (the same function run() calls per-URL at runtime)
    let comic;
    try {
      comic = runTransform(SANDBOX, parsed);
    } catch (e) {
      result.error_message = `processFeed() error: ${e.message}`;
      return result;
    }

    if (!comic || !comic.imageUrls || comic.imageUrls.length === 0) {
      result.error_message = 'No valid image found';
      return result;
    }

    // 5. Test hotlink protection on first image
    const imgUrl = comic.imageUrls[0];
    const accessible = await testImageAccess(imgUrl, url, timeout);
    if (!accessible) {
      result.error_message = 'Image has hotlink protection (403 Forbidden)';
      return result;
    }

    // 6. Build success result
    result.is_valid = true;
    result.comic_title = comic.title || null;
    result.image_url = imgUrl;
    result.image_source = detectImageSource(parsed, imgUrl);
    result.link = comic.link || extractLink(parsed);
    result.caption = comic.caption || null;

    return result;
  } catch (e) {
    result.error_message = `Request failed: ${e.message}`;
    return result;
  }
}

// ---------------------------------------------------------------------------
// Semaphore for concurrency control
// ---------------------------------------------------------------------------
class Semaphore {
  constructor(max) {
    this.max = max;
    this.current = 0;
    this.queue = [];
  }
  acquire() {
    return new Promise(resolve => {
      if (this.current < this.max) {
        this.current++;
        resolve();
      } else {
        this.queue.push(resolve);
      }
    });
  }
  release() {
    this.current--;
    if (this.queue.length > 0) {
      this.current++;
      this.queue.shift()();
    }
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  // Read JSON from stdin
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const input = JSON.parse(Buffer.concat(chunks).toString());

  const feeds = input.feeds || [];
  const timeout = input.timeout || 15000;
  const concurrency = input.concurrency || 20;

  process.stderr.write(`Validating ${feeds.length} feeds (concurrency=${concurrency}, timeout=${timeout}ms)\n`);

  const sem = new Semaphore(concurrency);
  let done = 0;

  const tasks = feeds.map(async ({ name, url }) => {
    await sem.acquire();
    try {
      const result = await validateFeed(name, url, timeout);
      done++;
    if (result.is_valid) {
      process.stderr.write(`[${done}/${feeds.length}] ✓ ${name}\n`);
    } else {
      process.stderr.write(`[${done}/${feeds.length}] ✗ ${name} — ${result.error_message}\n`);
    }
       return result;
    } finally {
      sem.release();
    }
  });

  const results = await Promise.all(tasks);
  process.stdout.write(JSON.stringify(results));
}

main().catch(err => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(1);
});
