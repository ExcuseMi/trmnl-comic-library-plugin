function transform(input) {
  const rss = input.rss.channel;
  const items = Array.isArray(rss.item) ? rss.item : [rss.item];
  
  // Filter items that have images
  const itemsWithImages = items.filter(item => {
    return item.enclosure?.url || item.description;
  });
  // Helper function to extract image URL from description HTML
  function getImageUrl(description) {
    if (!description) return null;
    
    const match = description.match(/src="([^"]+)"/);
    return match ? match[1] : null;
  }
  // Select item based on settings
  let selectedItem;
  if (input.trmnl.plugin_settings.custom_fields_values.only_show_latest) {
    selectedItem = itemsWithImages[0];
  } else {
    const randomIndex = Date.now() % itemsWithImages.length;
    selectedItem = itemsWithImages[randomIndex];
  }
  const imageUrl = selectedItem?.enclosure?.url || getImageUrl(selectedItem?.description);
  
  return {
    comic: {
      title: selectedItem?.title || "No comics found",
      imageUrl: imageUrl,
      description: selectedItem?.description || null,
      link: selectedItem?.link || null,
      pubDate: selectedItem?.pubDate || null
    }
  };
}