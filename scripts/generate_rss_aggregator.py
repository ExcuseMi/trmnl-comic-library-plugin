#!/usr/bin/env python3
"""
generate_rss_aggregator.py

Creates a single RSS feed item with multiple comic images.
Called from generate-options.py after validation.

The feed contains ONE item with 6 comic images (most recent or random).
Feed title: "Comic Library"
Item description: "All your comics in one plugin"
"""

import random
from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def generate_rss_aggregator(
        all_results: list,
        output_path: Path,
        count: int = 6,
        mode: str = "recent"
):
    """
    Generate an RSS feed with one item containing multiple comic images.

    Args:
        all_results: List of ValidationResult objects from validator
        output_path: Where to write comic_library.rss
        count: Number of comics to include (default 6)
        mode: "recent" for most recent, "random" for random selection
    """
    print(f"\n{'=' * 60}")
    print("GENERATING RSS AGGREGATOR FEED")
    print(f"{'=' * 60}")

    # Filter to only valid results with images
    valid_with_images = [r for r in all_results if r.image_url and not hasattr(r, 'error')]

    if len(valid_with_images) == 0:
        print("✗ No valid comics with images found")
        return

    # Select comics based on mode
    if mode == "random":
        selected = random.sample(valid_with_images, min(count, len(valid_with_images)))
        print(f"  Selected {len(selected)} random comics")
    else:  # recent
        selected = valid_with_images[:count]
        print(f"  Selected {len(selected)} most recent comics")

    # Build RSS 2.0 feed
    rss = Element('rss', version='2.0')
    rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
    rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')

    channel = SubElement(rss, 'channel')
    SubElement(channel, 'title').text = 'Comic Library'
    SubElement(channel, 'link').text = 'https://excusemi.github.io/trmnl-comic-library-plugin/'
    SubElement(channel, 'description').text = 'Daily comics aggregated into one feed'
    SubElement(channel, 'language').text = 'en'
    SubElement(channel, 'lastBuildDate').text = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')

    # Build HTML with all comic images
    content_html = ''
    for result in selected:
        comic_name = result.name or "Unknown"
        img_url = result.image_url
        comic_link = result.link or 'https://excusemi.github.io/trmnl-comic-library-plugin/'
        caption = result.caption or comic_name

        content_html += f'<div style="margin:20px 0; border:1px solid #ccc; padding:10px; border-radius:8px;">\n'
        content_html += f'  <h3 style="margin:0 0 10px 0;">{comic_name}</h3>\n'
        content_html += f'  <a href="{comic_link}" target="_blank"><img src="{img_url}" alt="{caption}" style="max-width:100%; height:auto;"/></a>\n'
        if caption and caption != comic_name:
            content_html += f'  <p style="margin:10px 0 0 0; font-style:italic; color:#666;">{caption}</p>\n'
        content_html += f'</div>\n'

    # Single item with all comics
    item = SubElement(channel, 'item')
    SubElement(item, 'title').text = 'Comic Library — Daily Comics'
    SubElement(item, 'link').text = 'https://excusemi.github.io/trmnl-comic-library-plugin/'

    # Put content in BOTH description and encoded for maximum compatibility
    SubElement(item, 'description').text = content_html
    SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded').text = content_html

    SubElement(item, 'pubDate').text = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    SubElement(item, 'guid', isPermaLink='false').text = f"comic-library-{datetime.utcnow().strftime('%Y%m%d')}"

    # Pretty print XML
    rough_string = tostring(rss, encoding='utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

    # Remove extra blank lines
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    pretty_xml = '\n'.join(lines)

    with open(output_path, 'wh', encoding='utf-8') as f:
        f.write(pretty_xml)

    print(f"✓ RSS feed written: {output_path}")
    print(f"  Contains {len(selected)} comics")
    print(f"  Feed URL: file://{output_path.absolute()}")


if __name__ == "__main__":
    print("This script is meant to be called from generate-options.py")
    print("It requires validated feed results as input.")