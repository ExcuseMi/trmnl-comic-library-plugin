import re

import requests
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
from datetime import datetime
import yaml
from pathlib import Path


@dataclass
class ValidationResult:
    """Result of RSS feed validation"""
    url: str
    is_valid: bool
    name: Optional[str] = None
    error_message: Optional[str] = None
    comic_title: Optional[str] = None
    image_url: Optional[str] = None
    image_source: Optional[str] = None  # 'enclosure' or 'description'
    feed_type: Optional[str] = None  # 'rss' or 'atom'
    link: Optional[str] = None
    caption: Optional[str] = None

class ImageExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image_url   = None
        self.image_title = None   # <img title="…">  — xkcd uses this
        self.image_alt   = None   # <img alt="…">

    def handle_starttag(self, tag, attrs):
        if tag == 'img' and not self.image_url:
            attrs_dict       = dict(attrs)
            self.image_url   = attrs_dict.get('src')
            self.image_title = attrs_dict.get('title')
            self.image_alt   = attrs_dict.get('alt')


class RSSFeedValidator:
    """Validates RSS and Atom feeds for comic plugin compatibility"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; ComicRSSValidator/1.0)'
        })

    @staticmethod
    def _extract_caption(parser: 'ImageExtractor', item_title: str | None,
                         feed_name: str | None, description_html: str | None = None) -> str | None:
        """Extract caption from image attributes or description HTML."""
        if parser is None:
            return None

        # First try to get caption from description HTML (for comics like The Far Side)
        if description_html:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(description_html, 'html.parser')
                img_tag = soup.find('img')
                if img_tag:
                    next_p = img_tag.find_next('p')
                    if next_p:
                        p_text = next_p.get_text().strip()
                        if p_text and 0 < len(p_text) <= 200:
                            # Filter out generic captions like "Comic strip for 2026/02/04"
                            if RSSFeedValidator._is_generic_caption(p_text):
                                return None

                            # Check if it looks like a comic caption
                            has_italic = (
                                    next_p.get('style', '').find('italic') != -1 or
                                    bool(next_p.find(['i', 'em'])) or
                                    '"' in p_text or '“' in p_text
                            )
                            if has_italic and not re.search(r"panel\s*\d+|^panel|narration|sfx|:",
                                                            p_text, re.IGNORECASE):
                                return p_text
            except:
                pass  # Fall back to image attributes

        # 1. <img title="…">  (xkcd style)
        if parser.image_title:
            text = parser.image_title.strip()
            if 0 < len(text) <= 200:
                # Filter out generic captions
                if not RSSFeedValidator._is_generic_caption(text):
                    return text

        # 2. Short alt, reject transcripts / generic echoes
        if parser.image_alt:
            text = parser.image_alt.strip()

            # looks like a transcript
            if re.search(r"panel\s*\d+|^panel|narration|sfx|\u2014|:", text, re.IGNORECASE):
                return None

            # just echoing the title/feed name back
            normalized = text.lower()
            bad = {t.lower() for t in (item_title, feed_name) if t}
            if normalized in bad:
                return None

            # single brand word like "Bizarro"
            if re.fullmatch(r"[A-Z][a-z]+", text):
                return None

            # Generic alt text (like "The Far Side comic")
            generic_phrases = {'comic', 'cartoon', 'image', 'picture', 'illustration'}
            if any(phrase in normalized for phrase in generic_phrases):
                return None

            # Filter out generic captions
            if RSSFeedValidator._is_generic_caption(text):
                return None

            if 0 < len(text) <= 140:
                return text

        return None

    @staticmethod
    def _is_generic_caption(caption: str) -> bool:
        """Check if a caption is generic (like 'Comic strip for 2026/02/04')."""
        if not caption:
            return True

        caption_lower = caption.lower().strip()

        # Generic comic descriptions
        generic_patterns = [
            r'^comic\s*(?:strip|panel)?\s*(?:for|from)?\s*\d{4}[/\\\-]\d{2}[/\\\-]\d{2}$',
            r'^comic\s*(?:strip|panel)?\s*(?:for|from)?\s*\w+\s+\d{1,2},\s*\d{4}$',
            r'^comic\s*(?:of|for)\s+the\s+day$',
            r'^daily\s+comic$',
            r'^today[^\w]*s?\s+comic$',
            r'^strip\s+for\s+\d{4}[/\\\-]\d{2}[/\\\-]\d{2}$',
            r'^for\s+\d{4}[/\\\-]\d{2}[/\\\-]\d{2}$',
        ]

        for pattern in generic_patterns:
            if re.match(pattern, caption_lower):
                return True

        # Generic phrases
        generic_phrases = [
            'comic strip for',
            'comic for',
            'daily comic',
            'today\'s comic',
            'this week\'s comic',
            'strip for',
            'panel for',
        ]

        for phrase in generic_phrases:
            if phrase in caption_lower:
                return True

        # Date-only patterns
        date_patterns = [
            r'^\d{4}[/\\\-]\d{2}[/\\\-]\d{2}$',
            r'^\w+\s+\d{1,2},\s*\d{4}$',
        ]

        for pattern in date_patterns:
            if re.match(pattern, caption_lower):
                return True

        return False

    def validate_feed(self, url: str, name: str = None) -> ValidationResult:
        """
        Validate a single RSS or Atom feed

        Args:
            url: RSS/Atom feed URL
            name: Optional name for logging

        Returns:
            ValidationResult object with validation details
        """
        display_name = name or url
        print(f"Validating: {display_name}", end=" ... ")

        try:
            # Fetch the feed
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Detect feed type
            if root.tag == 'rss' or root.tag.endswith('}rss'):
                return self._validate_rss_feed(root, url, name)
            elif root.tag == 'feed' or root.tag.endswith('}feed'):
                return self._validate_atom_feed(root, url, name)
            else:
                print(f"❌ Unknown feed type - {url}")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=False,
                    error_message=f"Unknown feed type: {root.tag}"
                )

        except requests.RequestException as e:
            print(f"❌ Request failed - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message=f"Request failed: {str(e)}"
            )
        except ET.ParseError as e:
            print(f"❌ XML parsing failed - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message=f"XML parsing failed: {str(e)}"
            )
        except Exception as e:
            print(f"❌ Unexpected error - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message=f"Unexpected error: {str(e)}"
            )

    def _test_image_access(self, image_url: str, feed_url: str) -> bool:
        """Test if image is accessible (check for hotlink protection)"""
        try:
            # Try to fetch the image with the feed URL as referrer
            response = self.session.head(
                image_url,
                timeout=5,
                headers={'Referer': feed_url},
                allow_redirects=True
            )

            # Check if we get 403 Forbidden
            if response.status_code == 403:
                return False
            elif response.status_code >= 400:
                # Try with GET in case HEAD is blocked
                response = self.session.get(
                    image_url,
                    timeout=5,
                    headers={'Referer': feed_url},
                    allow_redirects=True,
                    stream=True  # Don't download full image
                )
                response.close()

                if response.status_code == 403:
                    return False
                elif response.status_code >= 400:
                    return False

            return True

        except requests.RequestException:
            # If we can't test, assume it's accessible
            # (better to have false positive than false negative)
            return True

    def _validate_rss_feed(self, root: ET.Element, url: str, name: str = None) -> ValidationResult:
        """Validate an RSS feed"""
        # Find channel and items
        channel = root.find('channel')
        if channel is None:
            print(f"❌ No channel element - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="No channel element found in RSS",
                feed_type='rss'
            )

        items = channel.findall('item')
        if not items:
            print(f"❌ No items found - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="No items found in RSS feed",
                feed_type='rss'
            )

        first_item = items[0]
        title_elem = first_item.find('title')
        title = title_elem.text if title_elem is not None else "Untitled"

        # Extract link upfront — used in every valid return
        link_elem  = first_item.find('link')
        comic_link = link_elem.text if link_elem is not None else None

        # Resolve description and content:encoded upfront too —
        # we may need them for caption even when image comes from enclosure
        description      = first_item.find('description')
        content_encoded  = first_item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
        if content_encoded is None:
            content_encoded = first_item.find('content:encoded')

        # Check for generic promotional content
        if self._is_generic_promo_rss(first_item, title):
            print(f"❌ Generic promo content - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="Feed contains only generic promotional content",
                feed_type='rss'
            )

        # Try enclosure first (preferred method for the image)
        enclosure = first_item.find('enclosure')
        if enclosure is not None:
            image_url = enclosure.get('url')
            if image_url and self._is_valid_image_url(image_url):
                if not self._test_image_access(image_url, url):
                    print(f"❌ Hotlink protection - {url}")
                    return ValidationResult(
                        url=url,
                        name=name,
                        is_valid=False,
                        error_message="Image has hotlink protection (403 Forbidden)",
                        feed_type='rss'
                    )

                # Image came from enclosure, but caption lives in
                # description / content:encoded — run extractor on
                # the best available text just for that.
                caption_parser = None
                caption_text   = (content_encoded.text if content_encoded is not None else None) \
                              or (description.text      if description      is not None else None)
                if caption_text:
                    caption_parser = ImageExtractor()
                    caption_parser.feed(caption_text)

                print("✓ Valid (RSS enclosure)")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=True,
                    comic_title=title,
                    image_url=image_url,
                    image_source='enclosure',
                    feed_type='rss',
                    link=comic_link,
                    caption=self._extract_caption(caption_parser, title, name,
                                                  description_html=description.text)
                )

        # Try description
        if description is not None and description.text:
            parser = ImageExtractor()
            parser.feed(description.text)

            if parser.image_url and self._is_valid_image_url(parser.image_url):
                if not self._test_image_access(parser.image_url, url):
                    print(f"❌ Hotlink protection - {url}")
                    return ValidationResult(
                        url=url,
                        name=name,
                        is_valid=False,
                        error_message="Image has hotlink protection (403 Forbidden)",
                        feed_type='rss'
                    )

                print("✓ Valid (RSS description)")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=True,
                    comic_title=title,
                    image_url=parser.image_url,
                    image_source='description',
                    feed_type='rss',
                    link=comic_link,
                    caption=self._extract_caption(parser, title, name,
                                                  description_html=description.text),
                )

        # Try content:encoded (WordPress and other feeds use this)
        if content_encoded is not None and content_encoded.text:
            parser = ImageExtractor()
            parser.feed(content_encoded.text)

            if parser.image_url and self._is_valid_image_url(parser.image_url):
                if not self._test_image_access(parser.image_url, url):
                    print(f"❌ Hotlink protection - {url}")
                    return ValidationResult(
                        url=url,
                        name=name,
                        is_valid=False,
                        error_message="Image has hotlink protection (403 Forbidden)",
                        feed_type='rss'
                    )

                print("✓ Valid (RSS content:encoded)")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=True,
                    comic_title=title,
                    image_url=parser.image_url,
                    image_source='content:encoded',
                    feed_type='rss',
                    link=comic_link,
                    caption=self._extract_caption(parser, title, name),
                )

        # No valid image found
        print(f"❌ No valid image - {url}")
        return ValidationResult(
            url=url,
            name=name,
            is_valid=False,
            error_message="No valid image found in enclosure, description, or content:encoded",
            feed_type='rss'
        )

    def _validate_atom_feed(self, root: ET.Element, url: str, name: str = None) -> ValidationResult:
        """Validate an Atom feed"""
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        entries = root.findall('entry')
        if not entries:
            entries = root.findall('atom:entry', ns)

        if not entries:
            print(f"❌ No entries found - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="No entries found in Atom feed",
                feed_type='atom'
            )

        first_entry = entries[0]

        # title
        title_elem = first_entry.find('title')
        if title_elem is None:
            title_elem = first_entry.find('atom:title', ns)
        title = title_elem.text if title_elem is not None else "Untitled"

        # link  —  already needed for promo check, reuse for the result
        link_elem  = first_entry.find('link')
        if link_elem is None:
            link_elem = first_entry.find('atom:link', ns)
        comic_link = link_elem.get('href') if link_elem is not None else None

        # Check for generic promotional content
        if self._is_generic_promo_atom(first_entry, title, link_elem, ns):
            print(f"❌ Generic promo content - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="Feed contains only generic promotional content",
                feed_type='atom'
            )

        # summary / content
        summary = first_entry.find('summary')
        if summary is None:
            summary = first_entry.find('atom:summary', ns)

        content = first_entry.find('content')
        if content is None:
            content = first_entry.find('atom:content', ns)

        description_text = None
        if summary is not None and summary.text:
            description_text = summary.text
        elif content is not None and content.text:
            description_text = content.text

        if description_text:
            parser = ImageExtractor()
            parser.feed(description_text)

            if parser.image_url and self._is_valid_image_url(parser.image_url):
                if not self._test_image_access(parser.image_url, url):
                    print(f"❌ Hotlink protection - {url}")
                    return ValidationResult(
                        url=url,
                        name=name,
                        is_valid=False,
                        error_message="Image has hotlink protection (403 Forbidden)",
                        feed_type='atom'
                    )

                print("✓ Valid (Atom summary/content)")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=True,
                    comic_title=title,
                    image_url=parser.image_url,
                    image_source='summary',
                    feed_type='atom',
                    link=comic_link,
                    caption=self._extract_caption(parser, title, name),
                )

        # No valid image found
        print(f"❌ No valid image - {url}")
        return ValidationResult(
            url=url,
            name=name,
            is_valid=False,
            error_message="No valid image found in summary or content",
            feed_type='atom'
        )

    def _is_generic_promo_rss(self, item: ET.Element, title: str) -> bool:
        """Check if RSS item is generic promotional content"""
        link = item.find('link')
        link_has_date = False
        if link is not None and link.text:
            link_text = link.text
            if any(char.isdigit() for char in link_text.split('/')[-1]):
                link_has_date = True

        if not link_has_date:
            description = item.find('description')
            if description is not None and description.text:
                parser = ImageExtractor()
                parser.feed(description.text)
                if parser.image_url:
                    url_lower = parser.image_url.lower()
                    if 'generic_fb' in url_lower or 'social_fb_generic' in url_lower:
                        return True
                    if 'gocomicscmsassets' in url_lower and not link_has_date:
                        return True

            title_lower = title.lower() if title else ""
            desc_lower = description.text.lower() if description is not None and description.text else ""

            if 'explore the archive' in desc_lower and 'read extra content' in desc_lower:
                return True

        return False

    def _is_generic_promo_atom(self, entry: ET.Element, title: str, link_elem: Optional[ET.Element], ns: dict) -> bool:
        """Check if Atom entry is generic promotional content"""
        link_has_date = False

        if link_elem is not None:
            link_href = link_elem.get('href')
            if link_href and any(char.isdigit() for char in link_href.split('/')[-1]):
                link_has_date = True

        if not link_has_date:
            summary = entry.find('summary')
            if summary is None:
                summary = entry.find('atom:summary', ns)

            if summary is not None and summary.text:
                parser = ImageExtractor()
                parser.feed(summary.text)
                if parser.image_url:
                    url_lower = parser.image_url.lower()
                    if 'generic_fb' in url_lower or 'social_fb_generic' in url_lower:
                        return True
                    if 'gocomicscmsassets' in url_lower:
                        return True

                summary_lower = summary.text.lower()
                if 'explore the archive' in summary_lower and 'read extra content' in summary_lower:
                    return True

        return False

    def _is_valid_image_url(self, url: str) -> bool:
        """Check if URL looks like a valid image URL"""
        if not url:
            return False

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        return True

    def validate_multiple_feeds(self, feeds: Dict[str, str]) -> Tuple[List[ValidationResult], List[ValidationResult]]:
        """
        Validate multiple RSS/Atom feeds

        Args:
            feeds: Dictionary of {name: url}

        Returns:
            Tuple of (valid_results, invalid_results)
        """
        valid = []
        invalid = []

        for name, url in feeds.items():
            result = self.validate_feed(url, name)

            if result.is_valid:
                valid.append(result)
            else:
                invalid.append(result)

        return valid, invalid

    def print_summary(self, valid: List[ValidationResult], invalid: List[ValidationResult]):
        """Print validation summary"""
        total = len(valid) + len(invalid)
        if total == 0:
            print("\nNo feeds to validate")
            return

        print(f"\n{'=' * 60}")
        print(f"VALIDATION SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total feeds: {total}")
        print(f"✓ Valid: {len(valid)} ({len(valid) / total * 100:.1f}%)")
        print(f"✗ Invalid: {len(invalid)} ({len(invalid) / total * 100:.1f}%)")

    def save_failed_feeds_report(self, invalid_results: List[ValidationResult], output_path: Path):
        """Save a detailed report of failed RSS feeds"""
        if not invalid_results:
            print("\n✓ All feeds validated successfully! No failed feeds report needed.")
            return

        report = {
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_failed': len(invalid_results),
            'failed_feeds': []
        }

        for result in invalid_results:
            feed_info = {
                'name': result.name,
                'url': result.url,
                'error': result.error_message,
                'feed_type': result.feed_type,
                'status': 'needs_investigation'
            }
            report['failed_feeds'].append(feed_info)

        with open(output_path, 'w') as f:
            yaml.dump(report, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"\n⚠️  Failed feeds report saved to: {output_path}")
        print(f"   {len(invalid_results)} feed(s) need investigation")