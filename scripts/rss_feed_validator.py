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


class ImageExtractor(HTMLParser):
    """HTML parser to extract image URLs from description fields"""

    def __init__(self):
        super().__init__()
        self.image_url = None

    def handle_starttag(self, tag, attrs):
        if tag == 'img' and not self.image_url:
            attrs_dict = dict(attrs)
            self.image_url = attrs_dict.get('src')


class RSSFeedValidator:
    """Validates RSS and Atom feeds for comic plugin compatibility"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; ComicRSSValidator/1.0)'
        })

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

        # Try to extract image from first item
        first_item = items[0]
        title_elem = first_item.find('title')
        title = title_elem.text if title_elem is not None else "Untitled"

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

        # Try enclosure first (preferred method)
        enclosure = first_item.find('enclosure')
        if enclosure is not None:
            image_url = enclosure.get('url')
            if image_url and self._is_valid_image_url(image_url):
                # Test if image is accessible (check for hotlink protection)
                if not self._test_image_access(image_url, url):
                    print(f"❌ Hotlink protection - {url}")
                    return ValidationResult(
                        url=url,
                        name=name,
                        is_valid=False,
                        error_message="Image has hotlink protection (403 Forbidden)",
                        feed_type='rss'
                    )

                print("✓ Valid (RSS enclosure)")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=True,
                    comic_title=title,
                    image_url=image_url,
                    image_source='enclosure',
                    feed_type='rss'
                )

        # Try description
        description = first_item.find('description')
        if description is not None and description.text:
            parser = ImageExtractor()
            parser.feed(description.text)

            if parser.image_url and self._is_valid_image_url(parser.image_url):
                # Test if image is accessible
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
                    feed_type='rss'
                )

        # Try content:encoded (WordPress and other feeds use this)
        # Handle both with and without namespace
        content_encoded = first_item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
        if content_encoded is None:
            content_encoded = first_item.find('content:encoded')

        if content_encoded is not None and content_encoded.text:
            parser = ImageExtractor()
            parser.feed(content_encoded.text)

            if parser.image_url and self._is_valid_image_url(parser.image_url):
                # Test if image is accessible
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
                    feed_type='rss'
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
        # Handle namespaces
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        # Try without namespace first, then with
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

        # Try to extract image from first entry
        first_entry = entries[0]

        # Get title (try without namespace first, then with)
        title_elem = first_entry.find('title')
        if title_elem is None:
            title_elem = first_entry.find('atom:title', ns)
        title = title_elem.text if title_elem is not None else "Untitled"

        # Get link (for promo check)
        link_elem = first_entry.find('link')
        if link_elem is None:
            link_elem = first_entry.find('atom:link', ns)

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

        # Try to extract from summary or content
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
                # Test if image is accessible
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
                    feed_type='atom'
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
            # Check summary for generic content
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

        # Create report structure
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

        # Save to YAML
        with open(output_path, 'w') as f:
            yaml.dump(report, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"\n⚠️  Failed feeds report saved to: {output_path}")
        print(f"   {len(invalid_results)} feed(s) need investigation")