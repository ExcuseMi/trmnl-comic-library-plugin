// Fallback per-feed image selection strategies (used when remote config is unavailable)
// Key: substring of normalized feed title (lowercase, alphanumeric only)
// Value: strategy object with optional fields:
//   filter: 'numbered'       — keep only sequentially-numbered filenames (1.jpg, 2.jpg, …)
//   trim:   'first'|'last'   — remove one image from the start or end after filtering
//   pick:   'first'|'last'   — select a single image from the result
const FALLBACK_FEED_IMAGE_STRATEGIES = {};

// Captions that are too generic to be useful regardless of feed
const GENERIC_CAPTIONS = new Set([
  'cover image',
  'comic image',
  'strip image',
  'comic strip',
]);

/**
 * Determines if a given value looks like a valid RSS/Atom feed.
 */
function isFeed(obj) {
  return !!(obj && (obj.rss?.channel || obj.feed?.entry));
}

/**
 * Cleans a feed title by removing common platform suffixes.
 */
function cleanFeedTitle(title) {
  if (!title) return null;

  const platformSuffixes = [
    ' - GoComics',
    ' - TinyView',
    ' - Tapas',
    ' - Webtoons',
    ' - Comics Kingdom',
    ' - ComicsKingdom',
    ' - Creators',
    ' (GoComics)',
    ' (TinyView)',
    '.com'
  ];

  let cleaned = title;
  for (const suffix of platformSuffixes) {
    if (cleaned.endsWith(suffix)) {
      cleaned = cleaned.slice(0, -suffix.length);
      break;
    }
  }

  return cleaned.trim();
}

/**
 * Normalizes a feed title for strategy matching.
 */
function normalizeFeedKey(title) {
  if (!title) return '';
  return title.toLowerCase().replace(/[^a-z0-9]/g, '');
}

/**
 * Compares a title with a feed source in a flexible way.
 */
function isEquivalentToFeed(title, feed) {
  if (!title || !feed) return false;

  const normTitle = title.toLowerCase().replace(/[^a-z0-9]/g, '');
  const normFeed = feed.toLowerCase().replace(/[^a-z0-9]/g, '');
  if (normTitle === normFeed) return true;

  const articles = ['the', 'a', 'an'];
  for (const article of articles) {
    if (normFeed.startsWith(article)) {
      const stripped = normFeed.slice(article.length);
      if (stripped === normTitle) return true;
    }
    if (normTitle.startsWith(article)) {
      const stripped = normTitle.slice(article.length);
      if (stripped === normFeed) return true;
    }
  }
  return false;
}

/**
 * Extracts a readable title from a URL slug.
 */
function titleFromLink(link) {
  if (!link) return null;
  const segments = link.split('/').filter(Boolean);
  let i = segments.length - 1;
  while (i >= 0 && /^[\d-]+$/.test(segments[i])) i--;
  const slug = segments[i];
  if (!slug) return null;
  return slug.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

/**
 * Decodes HTML entities in a string.
 */
function decodeEntities(text) {
  return text
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'");
}

/**
 * Extracts image URLs from HTML content.
 */
function getImageUrls(html) {
  if (!html) return [];
  const regex = /src="([^"]+)"/g;
  const urls = [];
  let match;
  while ((match = regex.exec(html)) !== null) {
    urls.push(match[1]);
  }
  return urls;
}

/**
 * Filters out unlikely image URLs (e.g., containing decimal version numbers).
 */
function filterImages(urls) {
  if (urls.length <= 1) return urls;
  return urls.filter(url => {
    const filename = url.split('/').pop();
    return !/\d+\.\d+\./.test(filename);
  });
}

/**
 * Applies a feed‑specific image selection strategy.
 */
function applyImageStrategy(urls, strategy) {
  if (!strategy || urls.length === 0) return urls;

  let result = urls;

  if (strategy.filter === 'numbered') {
    const numbered = result.filter(url => /\/\d+\.\w+$/.test(url));
    if (numbered.length > 0) result = numbered;
  }

  if (strategy.trim === 'last' && result.length > 1) result = result.slice(0, -1);
  else if (strategy.trim === 'first' && result.length > 1) result = result.slice(1);

  if (strategy.pick === 'last') return [result[result.length - 1]];
  if (strategy.pick === 'first') return [result[0]];

  return result;
}

/**
 * Attempts to extract a meaningful caption from HTML content.
 */
function extractCaption(html, itemTitle, feedTitle) {
  if (!html) return null;

  const contextBadCaptions = [itemTitle?.toLowerCase(), feedTitle?.toLowerCase()].filter(Boolean);

  function isBadCaption(text) {
    if (!text || text.length === 0 || text.length > 200) return true;
    const n = text.toLowerCase();
    return (
      GENERIC_CAPTIONS.has(n) ||
      contextBadCaptions.includes(n) ||
      /comic strip for \d/i.test(text) ||
      /^[A-Z][a-z]+$/.test(text)
    );
  }

  // 1. Plain text (no HTML tags)
  if (!/<[a-z]/i.test(html)) {
    const text = decodeEntities(html.trim());
    return isBadCaption(text) ? null : text;
  }

  // 2. Italic paragraph tagline
  const italicParaMatch = html.match(/<p[^>]*font-style:\s*italic[^>]*>([^<]+)<\/p>/i);
  if (italicParaMatch?.[1]) {
    const text = decodeEntities(italicParaMatch[1]).trim();
    if (!isBadCaption(text)) return text;
  }

  // 3. <img title="">
  const titleMatch = html.match(/<img[^>]*title="([^"]*)"[^>]*>/i);
  if (titleMatch?.[1]) {
    const text = decodeEntities(titleMatch[1]).trim();
    if (!isBadCaption(text)) return text;
  }

  // 4. <img alt=""> – reject obvious transcripts
  const altMatch = html.match(/<img[^>]*alt="([^"]*)"[^>]*>/i);
  if (altMatch?.[1]) {
    const text = decodeEntities(altMatch[1]).trim();
    const looksLikeTranscript = /panel\s*\d+|^panel|narration|sfx|—|:|\bpanel\b/i.test(text);
    if (!looksLikeTranscript && !isBadCaption(text) && text.length <= 140) return text;
  }

  return null;
}

/**
 * Processes a single feed input and returns a comic object, or null if no image found.
 */
function processFeed(feedInput, parserConfig, trmnl) {
  let items = [];
  let isAtom = false;
  let feedTitle = null;

  if (feedInput.rss && feedInput.rss.channel) {
    items = Array.isArray(feedInput.rss.channel.item)
      ? feedInput.rss.channel.item
      : [feedInput.rss.channel.item];
    feedTitle = cleanFeedTitle(feedInput.rss.channel.title);
  } else if (feedInput.feed) {
    isAtom = true;
    items = Array.isArray(feedInput.feed.entry)
      ? feedInput.feed.entry
      : [feedInput.feed.entry];
    feedTitle = cleanFeedTitle(feedInput.feed.title);
  } else {
    return null;
  }

  items = items.filter(Boolean);
  if (items.length === 0) return null;

  const feedImageStrategies = parserConfig.feed_image_strategies || FALLBACK_FEED_IMAGE_STRATEGIES;

  function getDescription(item) {
    if (isAtom) {
      if (item.summary) {
        return typeof item.summary === 'string'
          ? item.summary
          : item.summary.__content__ || null;
      }
      if (item.content) {
        return typeof item.content === 'string'
          ? item.content
          : item.content.__content__ || null;
      }
      return null;
    } else {
      return item.encoded || item.description || null;
    }
  }

  function getLink(item) {
    if (isAtom) {
      if (!item.link) return null;
      return typeof item.link === 'string'
        ? item.link
        : item.link.href || null;
    }
    return item.link || null;
  }

  function getPubDate(item) {
    return isAtom
      ? item.updated || item.published || null
      : item.pubDate || null;
  }

  function getFeedImageStrategy(title) {
    const normalized = normalizeFeedKey(title);
    for (const [key, strategy] of Object.entries(feedImageStrategies)) {
      if (normalized.includes(key)) return strategy;
    }
    return null;
  }

  const itemsWithImages = items.filter(item => {
    const description = getDescription(item);
    const enclosureUrl = item.enclosure?.url;
    const descriptionUrls = getImageUrls(description);
    return enclosureUrl || descriptionUrls.length > 0;
  });

  if (itemsWithImages.length === 0) return null;

  let selectedItem;
  if (trmnl?.plugin_settings?.custom_fields_values?.only_show_latest === "true") {
    selectedItem = itemsWithImages[0];
  } else {
    selectedItem = itemsWithImages[Date.now() % itemsWithImages.length];
  }

  const description = getDescription(selectedItem);
  const enclosureUrl = selectedItem?.enclosure?.url;
  const strategy = getFeedImageStrategy(feedTitle);
  const imageUrls = enclosureUrl
    ? [enclosureUrl]
    : applyImageStrategy(filterImages(getImageUrls(description)), strategy);

  if (imageUrls.length === 0) return null;

  const rawTitle = selectedItem?.title ? decodeEntities(String(selectedItem.title)) : "";

  const titleIsDateStamped =
    /\s[-–]\s*\d{4}[-/]\d{2}[-/]\d{2}$/.test(rawTitle) ||
    /\sfor\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$/i.test(rawTitle) ||
    /\s+-\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$/i.test(rawTitle) ||
    /\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$/i.test(rawTitle);

  const hasRealTitle = rawTitle && rawTitle !== feedTitle && !titleIsDateStamped;
  const linkTitle = titleFromLink(getLink(selectedItem));
  let itemTitle = hasRealTitle
    ? rawTitle
    : (linkTitle !== feedTitle ? linkTitle : null) || feedTitle || rawTitle || "No comics found";

  const pubDate = getPubDate(selectedItem);
  const caption = extractCaption(description, selectedItem?.title, feedTitle);

  let finalTitle = itemTitle;
  let finalCaption = caption;

  if (finalTitle.length > 100) {
    if (!finalCaption) {
      finalCaption = finalTitle;
    }
    if (pubDate) {
      const date = new Date(pubDate);
      if (!isNaN(date.getTime())) {
        finalTitle = date.toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric'
        });
      } else {
        finalTitle = feedTitle || "Comic";
      }
    } else {
      finalTitle = feedTitle || "Comic";
    }
  } else {
    if (isEquivalentToFeed(finalTitle, feedTitle) && pubDate) {
      const date = new Date(pubDate);
      if (!isNaN(date.getTime())) {
        finalTitle = date.toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric'
        });
      }
    }
  }

  return {
    title: finalTitle,
    source: feedTitle,
    imageUrls,
    caption: finalCaption,
    link: getLink(selectedItem),
    pubDate
  };
}

// Same content as data/comic_parser_data.json — inlined so a single serverless
// invocation doesn't need an extra network round-trip just to fetch static config.
const PARSER_CONFIG = {
  feed_image_strategies: {
    adhdinos: { filter: 'numbered', trim: 'last' }
  }
};


// Hosted by the daily "Update Comic Options" GitHub Action (scripts/generate-options.py),
// which writes this alongside plugin/settings.yml's comics/comics_other_languages/
// comics_political options — same validated catalog, just as a flat array so it can be
// fetched instead of duplicated in code (and re-validated daily, unlike a baked-in copy).
const FULL_COMIC_POOL_URL = 'https://raw.githubusercontent.com/ExcuseMi/trmnl-comic-library-plugin/refs/heads/main/data/comic_urls.json';

async function fetchFullComicPool(deadline) {
  const budget = msUntil(deadline);
  if (budget <= 0) return [];
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.min(budget, 2000));
    const res = await fetch(FULL_COMIC_POOL_URL, { signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) return [];
    const urls = await res.json();
    return Array.isArray(urls) ? urls : [];
  } catch (err) {
    return [];
  }
}

/**
 * Parses a tag's attribute string ( key="value" key2='value2' ) into an object.
 * Namespace prefixes on attribute names are stripped to match fast-xml-parser's
 * removeNSPrefix behavior that the rest of this file (processFeed etc.) expects.
 */
function parseAttrs(str) {
  const attrs = {};
  if (!str) return attrs;
  const re = /([\w:-]+)\s*=\s*"([^"]*)"|([\w:-]+)\s*=\s*'([^']*)'/g;
  let m;
  while ((m = re.exec(str)) !== null) {
    const name = (m[1] || m[3]).replace(/^[\w-]+:/, '');
    attrs[name] = m[2] !== undefined ? m[2] : m[4];
  }
  return attrs;
}

/**
 * Finds all top-level occurrences of a tag (any namespace prefix) directly in `xml`.
 * Returns { attrs, content } per match — content is null for self-closing tags.
 * Not a real XML parser: doesn't track nesting depth, which is fine here since
 * RSS/Atom leaf elements (title, link, pubDate, enclosure, ...) never nest same-named tags.
 */
function findElements(xml, localName) {
  const results = [];
  const openRe = new RegExp('<(?:[\\w-]+:)?' + localName + '\\b([^>]*?)(\\/)?>', 'gi');
  let match;
  while ((match = openRe.exec(xml)) !== null) {
    const attrs = parseAttrs(match[1] || '');
    if (match[2]) {
      results.push({ attrs, content: null });
      continue;
    }
    const closeRe = new RegExp('<\\/(?:[\\w-]+:)?' + localName + '\\s*>', 'i');
    const rest = xml.slice(openRe.lastIndex);
    const closeMatch = rest.match(closeRe);
    if (closeMatch) {
      results.push({ attrs, content: rest.slice(0, closeMatch.index) });
      openRe.lastIndex += closeMatch.index + closeMatch[0].length;
    } else {
      results.push({ attrs, content: '' });
    }
  }
  return results;
}

/**
 * Unwraps CDATA and trims. Mirrors fast-xml-parser's trimValues:true,
 * processEntities:false — entities are deliberately left un-decoded here so
 * getImageUrls/extractCaption see the same raw markup they always have.
 */
function extractText(content) {
  if (content == null) return null;
  const cdata = content.match(/^\s*<!\[CDATA\[([\s\S]*?)\]\]>\s*$/);
  return cdata ? cdata[1] : content.trim();
}

function parseRssItem(itemXml) {
  const item = {};
  const title = findElements(itemXml, 'title')[0];
  if (title) item.title = extractText(title.content);
  const link = findElements(itemXml, 'link')[0];
  if (link) item.link = extractText(link.content);
  const pubDate = findElements(itemXml, 'pubDate')[0];
  if (pubDate) item.pubDate = extractText(pubDate.content);
  const description = findElements(itemXml, 'description')[0];
  if (description) item.description = extractText(description.content);
  const encoded = findElements(itemXml, 'encoded')[0]; // content:encoded, ns-stripped
  if (encoded) item.encoded = extractText(encoded.content);
  const enclosure = findElements(itemXml, 'enclosure')[0];
  if (enclosure) item.enclosure = enclosure.attrs;
  return item;
}

function parseRss(xml) {
  const channelEl = findElements(xml, 'channel')[0];
  if (!channelEl) return null;
  const channelXml = channelEl.content || '';
  const titleEl = findElements(channelXml, 'title')[0];
  const items = findElements(channelXml, 'item').map(el => parseRssItem(el.content || ''));
  return { rss: { channel: { title: titleEl ? extractText(titleEl.content) : null, item: items } } };
}

function parseAtomEntry(entryXml) {
  const entry = {};
  const title = findElements(entryXml, 'title')[0];
  if (title) entry.title = extractText(title.content);

  const links = findElements(entryXml, 'link');
  if (links.length > 0) {
    const preferred = links.find(l => l.attrs.rel !== 'self') || links[0];
    entry.link = Object.keys(preferred.attrs).length > 0 ? preferred.attrs : extractText(preferred.content);
  }

  const updated = findElements(entryXml, 'updated')[0];
  if (updated) entry.updated = extractText(updated.content);
  const published = findElements(entryXml, 'published')[0];
  if (published) entry.published = extractText(published.content);

  const summary = findElements(entryXml, 'summary')[0];
  if (summary) {
    entry.summary = Object.keys(summary.attrs).length > 0
      ? Object.assign({}, summary.attrs, { __content__: extractText(summary.content) })
      : extractText(summary.content);
  }
  const content = findElements(entryXml, 'content')[0];
  if (content) {
    entry.content = Object.keys(content.attrs).length > 0
      ? Object.assign({}, content.attrs, { __content__: extractText(content.content) })
      : extractText(content.content);
  }
  return entry;
}

function parseAtom(xml) {
  const feedEl = findElements(xml, 'feed')[0];
  if (!feedEl) return null;
  const feedXml = feedEl.content || '';
  const firstEntryIdx = feedXml.search(/<(?:[\w-]+:)?entry\b/i);
  const headerXml = firstEntryIdx === -1 ? feedXml : feedXml.slice(0, firstEntryIdx);
  const titleEl = findElements(headerXml, 'title')[0];
  const entries = findElements(feedXml, 'entry').map(el => parseAtomEntry(el.content || ''));
  return { feed: { title: titleEl ? extractText(titleEl.content) : null, entry: entries } };
}

/**
 * Parses raw RSS or Atom XML into the same shape TRMNL's polling engine used
 * to hand to transform() (fast-xml-parser with removeNSPrefix + processEntities:false),
 * so processFeed() and friends below don't need to change at all.
 */
function parseFeedXml(xml) {
  if (/<rss[\s>]/i.test(xml)) return parseRss(xml);
  if (/<feed[\s>]/i.test(xml)) return parseAtom(xml);
  return null;
}

// Every fetch in this file is given a slice of a single shared deadline (see run())
// instead of its own fixed timeout — otherwise a catalog fetch plus several batches
// of per-comic fetches could each take their own ~3.5s and blow well past the
// serverless runtime's 5s hard cap.
function msUntil(deadline) {
  return Math.max(0, deadline - Date.now());
}

async function fetchFeedXml(url, deadline) {
  const budget = msUntil(deadline);
  if (budget <= 0) return null;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.min(budget, 3500));
    const res = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; TRMNLComicLibrary/1.0)' },
      redirect: 'follow',
      signal: controller.signal
    });
    clearTimeout(timer);
    // Non-2xx (dead feed, renamed slug, ...) — caller treats this the same as
    // "no comic" and moves on to another URL from the pool instead of failing.
    if (!res.ok) return null;
    return await res.text();
  } catch (err) {
    return null;
  }
}

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function parseMultiSelect(value) {
  if (!value) return [];
  try {
    const arr = JSON.parse(value);
    return Array.isArray(arr) ? arr.filter(Boolean) : [];
  } catch (e) {
    return [];
  }
}

/**
 * Fetches, parses and transforms a single feed URL into a comic (or null on any failure).
 */
async function fetchAndProcessComic(url, trmnl, deadline) {
  const xml = await fetchFeedXml(url, deadline);
  if (!xml) return null;
  const parsed = parseFeedXml(xml);
  if (!isFeed(parsed)) return null;
  return processFeed(parsed, PARSER_CONFIG, trmnl);
}

/**
 * Main entry point (TRMNL Serverless). Builds the candidate feed pool from the
 * user's settings, then fetches in shuffled batches — a bad/dead URL just gets
 * dropped and the next candidate from the pool fills its slot, up to a time
 * budget that stays safely under the 5s serverless hard cap.
 */
async function run(input) {
  // Single shared deadline for the whole invocation — headroom under the 5s
  // serverless hard cap, covering the optional catalog fetch below AND every
  // comic fetch batch, so no combination of them can run long past 5s total.
  const deadline = Date.now() + 4300;

  const settings = (input && input.trmnl && input.trmnl.plugin_settings && input.trmnl.plugin_settings.custom_fields_values) || {};
  const trmnl = input && input.trmnl;

  let pool = []
    .concat(parseMultiSelect(settings.comics))
    .concat(parseMultiSelect(settings.comics_other_languages))
    .concat(parseMultiSelect(settings.comics_political))
    .concat((settings.extra_rss_feeds || '').split(',').map(s => s.trim()).filter(Boolean));

  pool = pool.filter((url, i) => pool.indexOf(url) === i); // de-dupe, keep order

  if (pool.length === 0) {
    pool = await fetchFullComicPool(deadline);
  }
  if (pool.length === 0) {
    pool = ['https://xkcd.com/atom.xml']; // catalog fetch failed too — last resort so the render isn't empty
  }

  shuffle(pool);

  const TARGET = 10;
  const BATCH_SIZE = 15;

  const comics = [];
  let offset = 0;

  while (comics.length < TARGET && offset < pool.length && msUntil(deadline) > 0) {
    const batch = pool.slice(offset, offset + BATCH_SIZE);
    offset += batch.length;

    const results = await Promise.all(batch.map(url => fetchAndProcessComic(url, trmnl, deadline)));
    for (const comic of results) {
      if (comic) comics.push(comic);
      if (comics.length >= TARGET) break;
    }
  }

  return { comics };
}