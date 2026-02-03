#!/usr/bin/env python3
"""
generate_rss_aggregator.py

Creates an Atom feed with ONE entry containing multiple comic images.
Can be run standalone or imported as a library.

Standalone: python scripts/generate_rss_aggregator.py [--count 6] [--mode recent]
Library:    from generate_rss_aggregator import generate_atom_feed
"""

import json
import random
import argparse
from pathlib import Path
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def generate_atom_feed(
        comics: list[dict],
        output_path: Path,
        count: int = 6,
        mode: str = "recent"
):
    """
    Generate an Atom feed with ONE entry containing multiple comic images.

    Args:
        comics: List of comic dicts with keys: name, image_url, link, caption, title
        output_path: Where to write demo_data.atom
        count: Number of comics to include (default 6)
        mode: "recent" for first N, "random" for random selection
    """
    print(f"\n{'=' * 60}")
    print("GENERATING ATOM FEED")
    print(f"{'=' * 60}")

    # Filter to only comics with images
    valid = [c for c in comics if c.get('image_url') and not c.get('error')]

    if len(valid) == 0:
        print("✗ No valid comics with images found")
        return

    # Select comics based on mode
    if mode == "random":
        selected = random.sample(valid, min(count, len(valid)))
        print(f"  Selected {len(selected)} random comics")
    else:  # recent
        selected = valid[:count]
        print(f"  Selected {len(selected)} most recent comics")

    # Build Atom feed
    feed = Element('feed')
    feed.set('xmlns', 'http://www.w3.org/2005/Atom')
    feed.set('xml:lang', 'en')

    SubElement(feed, 'title').text = 'Comic Library'

    link = SubElement(feed, 'link')
    link.set('href', 'https://excusemi.github.io/trmnl-comic-library-plugin/')
    link.set('rel', 'alternate')

    SubElement(feed, 'id').text = 'https://excusemi.github.io/trmnl-comic-library-plugin/'
    SubElement(feed, 'updated').text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Create ONE entry with all comics inside
    entry = SubElement(feed, 'entry')

    SubElement(entry, 'title').text = 'Comic Library — Daily Comics'

    entry_link = SubElement(entry, 'link')
    entry_link.set('href', 'https://excusemi.github.io/trmnl-comic-library-plugin/')
    entry_link.set('rel', 'alternate')

    SubElement(entry, 'updated').text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    SubElement(entry, 'id').text = f'comic-library-{datetime.now(timezone.utc).strftime("%Y%m%d")}'

    # Build HTML with ALL images in one summary
    summary = SubElement(entry, 'summary')
    summary.set('type', 'html')

    html = ''
    for comic in selected:
        img_url = comic.get('image_url')
        comic_name = comic.get('name') or 'Unknown'
        comic_title = comic.get('title') or comic_name
        caption = comic.get('caption') or comic_title

        # Each image on its own line with title/alt for caption
        html += f'<img src="{img_url}" title="{caption}" alt="{caption}" /><br/>'

    # Keep HTML escaped - it will become __content__ string like xkcd
    summary.text = html

    # Pretty print XML
    rough_string = tostring(feed, encoding='utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

    # Remove extra blank lines
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    pretty_xml = '\n'.join(lines)

    # NOTE: We do NOT un-escape HTML here. Keeping it escaped (&lt;img&gt;) makes
    # the parser store it as __content__ string (like xkcd) instead of parsing it
    # into structured objects. The transform's regex will work on the __content__ string.

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)

    print(f"✓ Atom feed written: {output_path}")
    print(f"  Contains 1 entry with {len(selected)} images")


def _resolve_base() -> Path:
    """Root of the repo, whether we're run from scripts/ or from root."""
    here = Path(__file__).resolve().parent
    return here.parent if here.name == "scripts" else here


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Atom feed from comic_overview_data.json"
    )
    parser.add_argument("--json", type=Path,
                        help="Path to comic_overview_data.json (default: data/comic_overview_data.json)")
    parser.add_argument("--output", type=Path,
                        help="Output path (default: data/demo_data.atom)")
    parser.add_argument("--count", type=int, default=6,
                        help="Number of comics to include (default: 6)")
    parser.add_argument("--mode", choices=["recent", "random"], default="recent",
                        help="Selection mode: recent or random (default: recent)")
    args = parser.parse_args()

    base = _resolve_base()
    json_path = args.json or base / "data" / "comic_overview_data.json"
    output_path = args.output or base / "data" / "demo_data.atom"

    if not json_path.exists():
        print(f"✗ JSON not found: {json_path}")
        print("  Run generate-options.py first to create it.")
        raise SystemExit(1)

    with open(json_path, encoding='utf-8') as f:
        comics = json.load(f)

    print(f"[*] Loaded {len(comics)} comics from {json_path}")

    generate_atom_feed(
        comics=comics,
        output_path=output_path,
        count=args.count,
        mode=args.mode
    )

    print(f"\n[*] Feed URL: {output_path.absolute()}")
    print("[*] Use this as a polling URL in your TRMNL private plugin")