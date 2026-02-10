function transform(input) {
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

  if (input.rss && input.rss.channel) {
    items = Array.isArray(input.rss.channel.item)
      ? input.rss.channel.item
      : [input.rss.channel.item];
    feedTitle = cleanFeedTitle(input.rss.channel.title);
  } else if (input.feed) {
    isAtom = true;
    items = Array.isArray(input.feed.entry)
      ? input.feed.entry
      : [input.feed.entry];
    feedTitle = cleanFeedTitle(input.feed.title);
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

  function extractCaption(html, itemTitle, feedTitle) {
    if (!html) return null;

    // 1. Prefer <img title=""> (xkcd-style)
    const titleMatch = html.match(/<img[^>]*title="([^"]*)"[^>]*>/i);
    if (titleMatch && titleMatch[1]) {
      const text = decodeEntities(titleMatch[1]).trim();
      if (text.length > 0 && text.length <= 200) {
        return text;
      }
    }

    // 2. Very short alt text ONLY (reject transcripts + generic names)
    const altMatch = html.match(/<img[^>]*alt="([^"]*)"[^>]*>/i);
    if (altMatch && altMatch[1]) {
      const text = decodeEntities(altMatch[1]).trim();

      const looksLikeTranscript =
        /panel\s*\d+|^panel|narration|sfx|—|:|\bpanel\b/i.test(text);

      const normalized = text.toLowerCase();
      const badCaptions = [
        itemTitle?.toLowerCase(),
        feedTitle?.toLowerCase()
      ].filter(Boolean);

      const isGeneric =
        badCaptions.includes(normalized) ||
        /^[A-Z][a-z]+$/.test(text); // single-word brand like "Bizarro"

      if (
        !looksLikeTranscript &&
        !isGeneric &&
        text.length > 0 &&
        text.length <= 140
      ) {
        return text;
      }
    }

    // 3. No caption (preferred over bad caption)
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
  const imageUrls = enclosureUrl
    ? [enclosureUrl]
    : filterImages(getImageUrls(description));

  return {
    comic: {
      title: selectedItem?.title + "" || "No comics found",
      source: feedTitle,
      imageUrls,
      caption: extractCaption(
        description,
        selectedItem?.title,
        feedTitle
      ),
      link: getLink(selectedItem),
      pubDate: getPubDate(selectedItem)
    }
  };
}
