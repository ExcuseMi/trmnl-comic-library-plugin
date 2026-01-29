function transform(input) {
  // Detect feed type and normalize structure
  let items = [];
  let isAtom = false;
  let feedTitle = null;
  
  // Helper to clean feed title by removing platform suffixes and redundant parts
  function cleanFeedTitle(title) {
    if (!title) return null;
    
    // Remove common platform suffixes
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
    // RSS feed
    items = Array.isArray(input.rss.channel.item) ? input.rss.channel.item : [input.rss.channel.item];
    feedTitle = cleanFeedTitle(input.rss.channel.title);
  } else if (input.feed) {
    // Atom feed
    isAtom = true;
    items = Array.isArray(input.feed.entry) ? input.feed.entry : [input.feed.entry];
    feedTitle = cleanFeedTitle(input.feed.title);
  } else {
    return {
      comic: {
        title: "No comics found",
        source: null,
        imageUrls: [],
        caption: null,
        link: null,
        pubDate: null
      }
    };
  }
  
  // Filter out undefined/null items
  items = items.filter(item => item != null);
  
  if (items.length === 0) {
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
  
  // Helper function to extract all image URLs from description/summary HTML
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
  
  // Helper function to filter out obvious non-panel images
  function filterImages(urls) {
    if (urls.length <= 1) return urls;
    
    // Remove images with .X.X. patterns (like 5.5.jpg)
    return urls.filter(url => {
      const filename = url.split('/').pop();
      return !/\d+\.\d+\./.test(filename);
    });
  }
  
  // Helper function to extract caption text from HTML
  function extractCaption(html) {
    if (!html) return null;
    
    // First try to get title attribute from img tag (XKCD style)
    const imgMatch = html.match(/<img[^>]*title="([^"]*)"[^>]*>/i);
    if (imgMatch && imgMatch[1]) {
      let text = imgMatch[1];
      
      // Decode HTML entities
      text = text.replace(/&quot;/g, '"')
                 .replace(/&amp;/g, '&')
                 .replace(/&lt;/g, '<')
                 .replace(/&gt;/g, '>')
                 .replace(/&nbsp;/g, ' ')
                 .replace(/&#39;/g, "'")
                 .replace(/&apos;/g, "'");
      
      text = text.trim();
      if (text && text.length > 0 && text.length <= 500) {
        return text;
      }
    }
    
    // Fallback: try to extract from <p> tags
    let text = html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
    text = text.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
    text = text.replace(/<img[^>]*>/gi, '');
    text = text.replace(/<div class="comic-gallery"[^>]*>/gi, '');
    text = text.replace(/<div class="comic-panel"[^>]*>/gi, '');
    text = text.replace(/<div class="panel-description"[^>]*>/gi, '');
    text = text.replace(/<\/div>/gi, '');
    text = text.replace(/<a[^>]*>/gi, '');
    text = text.replace(/<\/a>/gi, '');
    
    const pMatch = text.match(/<p[^>]*>(.*?)<\/p>/i);
    if (pMatch && pMatch[1]) {
      text = pMatch[1];
    } else {
      text = text.replace(/<[^>]+>/g, ' ');
    }
    
    // Decode HTML entities
    text = text.replace(/&quot;/g, '"')
               .replace(/&amp;/g, '&')
               .replace(/&lt;/g, '<')
               .replace(/&gt;/g, '>')
               .replace(/&nbsp;/g, ' ')
               .replace(/&#39;/g, "'")
               .replace(/&apos;/g, "'");
    
    // Clean up whitespace
    text = text.replace(/\s+/g, ' ').trim();
    
    // Remove "alt-text:" prefix if present
    text = text.replace(/^alt-text:\s*/i, '');
    
    // Filter out generic promotional text
    const genericPhrases = [
      'comic strip for',
      'visit the',
      '© ',
      'explore the archive',
      'read extra content'
    ];
    
    const textLower = text.toLowerCase();
    for (const phrase of genericPhrases) {
      if (textLower.includes(phrase)) {
        const quoteMatch = text.match(/[""]([^""]+)[""]/);
        if (quoteMatch && quoteMatch[1]) {
          return quoteMatch[1];
        }
        if (text.length < 200) {
          return null;
        }
      }
    }
    
    if (text.length > 500) {
      return null;
    }
    
    return text || null;
  }
  
  // Helper to get description/summary from item
  function getDescription(item) {
    if (isAtom) {
      // Atom feeds use summary or content with __content__ property
      if (item.summary) {
        if (typeof item.summary === 'string') {
          return item.summary;
        } else if (item.summary.__content__) {
          return item.summary.__content__;
        }
      }
      if (item.content) {
        if (typeof item.content === 'string') {
          return item.content;
        } else if (item.content.__content__) {
          return item.content.__content__;
        }
      }
      return null;
    } else {
      // RSS feeds use description
      return item.description || null;
    }
  }
  
  // Helper to get link from item
  function getLink(item) {
    if (isAtom) {
      // Atom link is an object with href property
      if (item.link) {
        if (typeof item.link === 'string') {
          return item.link;
        } else if (item.link.href) {
          return item.link.href;
        }
      }
      return null;
    } else {
      return item.link || null;
    }
  }
  
  // Helper to get pubDate from item
  function getPubDate(item) {
    if (isAtom) {
      return item.updated || item.published || null;
    } else {
      return item.pubDate || null;
    }
  }
  
  // Filter items that have images
  const itemsWithImages = items.filter(item => {
    const description = getDescription(item);
    const enclosureUrl = item.enclosure?.url;
    const descriptionUrls = getImageUrls(description);
    return enclosureUrl || descriptionUrls.length > 0;
  });
  
  if (itemsWithImages.length === 0) {
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
  
  // Select item based on settings
  let selectedItem;
  if (input.trmnl.plugin_settings.custom_fields_values.only_show_latest === "yes") {
    selectedItem = itemsWithImages[0];
  } else {
    const randomIndex = Date.now() % itemsWithImages.length;
    selectedItem = itemsWithImages[randomIndex];
  }
  
  const description = getDescription(selectedItem);
  
  // Extract all image URLs
  const imageUrls = getImageUrls(description);
  const enclosureUrl = selectedItem?.enclosure?.url;
  
  // Use enclosure if available, otherwise filter images from description
  let finalImageUrls;
  if (enclosureUrl) {
    finalImageUrls = [enclosureUrl];
  } else {
    finalImageUrls = filterImages(imageUrls);
  }
  
  // Extract caption
  const caption = extractCaption(description);
  
  return {
    comic: {
      title: selectedItem?.title || "No comics found",
      source: feedTitle,
      imageUrls: finalImageUrls,
      caption: caption,
      link: getLink(selectedItem),
      pubDate: getPubDate(selectedItem)
    }
  };
}