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

function transform(input) {
  // Support multi-URL polling: IDX_0 = config JSON, IDX_1 = RSS/Atom feed
  // Fall back to input directly for single-URL mode (backwards compatibility)
  const parserConfig = input.IDX_0 || {};
  const feedInput = input.IDX_1 || input;
  const feedImageStrategies = parserConfig.feed_image_strategies || FALLBACK_FEED_IMAGE_STRATEGIES;

  let items = [];
  let isAtom = false;
  let feedTitle = null;

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
    return emptyResult();
  }

  items = items.filter(Boolean);
  if (items.length === 0) return emptyResult();

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

  function filterImages(urls) {
    if (urls.length <= 1) return urls;
    return urls.filter(url => {
      const filename = url.split('/').pop();
      return !/\d+\.\d+\./.test(filename);
    });
  }

  function normalizeFeedKey(title) {
    if (!title) return '';
    return title.toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  function getFeedImageStrategy(title) {
    const normalized = normalizeFeedKey(title);
    for (const [key, strategy] of Object.entries(feedImageStrategies)) {
      if (normalized.includes(key)) return strategy;
    }
    return null;
  }

  function applyImageStrategy(urls, strategy) {
    if (!strategy || urls.length === 0) return urls;

    let result = urls;

    // filter: keep only sequentially-numbered filenames (1.jpg, 2.jpg, …)
    if (strategy.filter === 'numbered') {
      const numbered = result.filter(url => /\/\d+\.\w+$/.test(url));
      if (numbered.length > 0) result = numbered;
    }

    // trim: remove one image from start or end
    if (strategy.trim === 'last' && result.length > 1) result = result.slice(0, -1);
    else if (strategy.trim === 'first' && result.length > 1) result = result.slice(1);

    // pick: select a single image
    if (strategy.pick === 'last') return [result[result.length - 1]];
    if (strategy.pick === 'first') return [result[0]];

    return result;
  }

  function extractCaption(html, itemTitle, feedTitle) {
    if (!html) return null;

    const contextBadCaptions = [itemTitle?.toLowerCase(), feedTitle?.toLowerCase()].filter(Boolean);

    function isBadCaption(text) {
      if (!text || text.length === 0 || text.length > 200) return true;
      const n = text.toLowerCase();
      return (
        GENERIC_CAPTIONS.has(n) ||
        contextBadCaptions.includes(n) ||
        /comic strip for \d/i.test(text) ||   // GoComics date e.g. "Comic strip for 2026/03/12"
        /^[A-Z][a-z]+$/.test(text)            // single-word brand like "Bizarro"
      );
    }

    // 1. Plain text (no HTML tags) — e.g. TinyView direct feed descriptions
    if (!/<[a-z]/i.test(html)) {
      const text = decodeEntities(html.trim());
      return isBadCaption(text) ? null : text;
    }

    // 2. Italic paragraph tagline (e.g. TinyView/ADHDinos ComicCaster style)
    const italicParaMatch = html.match(/<p[^>]*font-style:\s*italic[^>]*>([^<]+)<\/p>/i);
    if (italicParaMatch?.[1]) {
      const text = decodeEntities(italicParaMatch[1]).trim();
      if (!isBadCaption(text)) return text;
    }

    // 3. <img title=""> (xkcd-style)
    const titleMatch = html.match(/<img[^>]*title="([^"]*)"[^>]*>/i);
    if (titleMatch?.[1]) {
      const text = decodeEntities(titleMatch[1]).trim();
      if (!isBadCaption(text)) return text;
    }

    // 4. <img alt=""> — reject transcripts too
    const altMatch = html.match(/<img[^>]*alt="([^"]*)"[^>]*>/i);
    if (altMatch?.[1]) {
      const text = decodeEntities(altMatch[1]).trim();
      const looksLikeTranscript = /panel\s*\d+|^panel|narration|sfx|—|:|\bpanel\b/i.test(text);
      if (!looksLikeTranscript && !isBadCaption(text) && text.length <= 140) return text;
    }

    return null;
  }

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

  function emptyResult() {
    return {
      comic: {
        title: "No comics found",
        source: feedTitle,
        imageUrls: [],
        caption: null,
        link: null,
        pubDate: null
      }
    };
  }

  // Helper to compare title and feed source more flexibly
  function isEquivalentToFeed(title, feed) {
    if (!title || !feed) return false;

    // Normalize both: lowercase, remove all non-alphanumeric
    const normTitle = title.toLowerCase().replace(/[^a-z0-9]/g, '');
    const normFeed = feed.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (normTitle === normFeed) return true;

    // Try removing common leading articles from the feed and compare
    const articles = ['the', 'a', 'an'];
    for (const article of articles) {
      if (normFeed.startsWith(article)) {
        const stripped = normFeed.slice(article.length);
        if (stripped === normTitle) return true;
      }
      // Also check if title starts with article and stripped matches feed
      if (normTitle.startsWith(article)) {
        const stripped = normTitle.slice(article.length);
        if (stripped === normFeed) return true;
      }
    }
    return false;
  }

  const itemsWithImages = items.filter(item => {
    const description = getDescription(item);
    const enclosureUrl = item.enclosure?.url;
    const descriptionUrls = getImageUrls(description);
    return enclosureUrl || descriptionUrls.length > 0;
  });

  if (itemsWithImages.length === 0) return emptyResult();

  let selectedItem;
  if (input.trmnl?.plugin_settings?.custom_fields_values?.only_show_latest === "true") {
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

  function titleFromLink(link) {
    if (!link) return null;
    const segments = link.split('/').filter(Boolean);
    // Walk backwards past pure date/number segments (e.g. /2026/03/12)
    let i = segments.length - 1;
    while (i >= 0 && /^[\d-]+$/.test(segments[i])) i--;
    const slug = segments[i];
    if (!slug) return null;
    return slug.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }

  const rawTitle = decodeEntities(selectedItem?.title + "");

  // Expanded date‑stamped detection: covers " - 2026-03-12", " for Mar 12, 2026", " - Mar 12, 2026", and " Mar 12, 2026"
  const titleIsDateStamped =
    /\s[-–]\s*\d{4}[-/]\d{2}[-/]\d{2}$/.test(rawTitle) ||          // " - 2026-03-12"
    /\sfor\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$/i.test(rawTitle) || // " for Mar 12, 2026"
    /\s+-\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$/i.test(rawTitle) ||  // " - Mar 12, 2026"
    /\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$/i.test(rawTitle);        // " Mar 12, 2026"

  const hasRealTitle = rawTitle && rawTitle !== feedTitle && !titleIsDateStamped;
  const linkTitle = titleFromLink(getLink(selectedItem));
  let itemTitle = hasRealTitle
    ? rawTitle
    : (linkTitle !== feedTitle ? linkTitle : null) || feedTitle || rawTitle || "No comics found";

  const pubDate = getPubDate(selectedItem);
  const caption = extractCaption(description, selectedItem?.title, feedTitle);

  // Final title and caption, with two overrides:
  // 1. If the computed title is longer than 100 characters, move it to caption (if empty) and use date/feed as title.
  // 2. If title is equivalent to feed source (flexible comparison), replace with nicely formatted date.
  let finalTitle = itemTitle;
  let finalCaption = caption;

  if (finalTitle.length > 100) {
    // Move long title to caption if no caption yet
    if (!finalCaption) {
      finalCaption = finalTitle;
    }
    // Set title to date if available, else feed name
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
    // Flexible title‑vs‑feed equivalence check
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
    comic: {
      title: finalTitle,
      source: feedTitle,
      imageUrls,
      caption: finalCaption,
      link: getLink(selectedItem),
      pubDate
    }
  };
}