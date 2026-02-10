'use strict';

const fs = require('fs');
const vm = require('vm');
const { XMLParser } = require('fast-xml-parser');

// ---------------------------------------------------------------------------
// Load transform.js from the same directory (copied in at Docker build time)
// ---------------------------------------------------------------------------
const transformCode = fs.readFileSync(__dirname + '/transform.js', 'utf-8');

function runTransform(parsedXml) {
  // Create a fresh sandbox with Date.now returning 0 so transform always
  // picks the first (most recent) item — matching validation expectations.
  const sandbox = {
    Date: { now: () => 0 },
    Array, Object, String, Number, Boolean, RegExp, Math, JSON,
    parseInt, parseFloat, isNaN, isFinite, undefined,
  };
  vm.createContext(sandbox);

  // Define the transform function inside the sandbox, then call it.
  vm.runInContext(transformCode, sandbox);
  return vm.runInContext('transform(__input__)', Object.assign(sandbox, { __input__: parsedXml }));
}

// ---------------------------------------------------------------------------
// XML parser — configured to match TRMNL's fast-xml-parser behaviour
// ---------------------------------------------------------------------------
const xmlParser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '',
  textNodeName: '__content__',
  removeNSPrefix: true,
  trimValues: true,
});

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

    // 2. Parse XML → JSON
    let parsed;
    try {
      parsed = xmlParser.parse(xml);
    } catch (e) {
      result.error_message = `XML parsing failed: ${e.message}`;
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

    // 4. Run transform()
    let transformResult;
    try {
      transformResult = runTransform(parsed);
    } catch (e) {
      result.error_message = `transform() error: ${e.message}`;
      return result;
    }

    const comic = transformResult?.comic;
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
      const symbol = result.is_valid ? '\u2713' : '\u2717';
      process.stderr.write(`[${done}/${feeds.length}] ${symbol} ${name}\n`);
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
