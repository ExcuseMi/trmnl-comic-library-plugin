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

  const rawTitle = decodeEntities(selectedItem?.title + "");

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

/**
 * Main transform function – supports multiple feeds via IDX_1, IDX_2, … and returns up to 5 comics.
 */
function transform(input) {
  // Extract configuration from IDX_0 if present
  const parserConfig = (input.IDX_0 && typeof input.IDX_0 === 'object' && !isFeed(input.IDX_0))
    ? input.IDX_0
    : {};

  // Collect all feed inputs
  const feedInputs = [];

  // If there are IDX_ properties, treat them as feeds (excluding IDX_0)
  const idxKeys = Object.keys(input).filter(k => /^IDX_\d+$/.test(k) && k !== 'IDX_0');
  if (idxKeys.length > 0) {
    for (const key of idxKeys) {
      const val = input[key];
      if (isFeed(val)) {
        feedInputs.push(val);
      }
    }
  } else {
    // No IDX_ properties – assume the input itself is a single feed
    if (isFeed(input)) {
      feedInputs.push(input);
    }
  }

  // Process each feed, collect up to 10 valid comics
  const comics = [];
  for (const feedInput of feedInputs) {
    if (comics.length > 10) break;
    const comic = processFeed(feedInput, parserConfig, input.trmnl);
    if (comic) {
      comics.push(comic);
    }
  }

  return { comics };
}