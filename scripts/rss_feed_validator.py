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
    """Validates RSS feeds for comic plugin compatibility"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; ComicRSSValidator/1.0)'
        })

def validate_feed(self, url: str, name: str = None) -> ValidationResult:
    """
    Validate a single RSS feed

    Args:
        url: RSS feed URL
        name: Optional name for logging

    Returns:
        ValidationResult object with validation details
    """
    display_name = name or url
    print(f"Validating: {display_name}", end=" ... ")

    try:
        # Fetch the RSS feed
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.content)

        # Find channel and items
        channel = root.find('channel')
        if channel is None:
            print(f"❌ No channel element - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="No channel element found in RSS"
            )

        items = channel.findall('item')
        if not items:
            print(f"❌ No items found - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="No items found in RSS feed"
            )

        # Try to extract image from first item
        first_item = items[0]
        title_elem = first_item.find('title')
        title = title_elem.text if title_elem is not None else "Untitled"
        
        # Check for generic promotional content
        if self._is_generic_promo(first_item, title):
            print(f"❌ Generic promo content - {url}")
            return ValidationResult(
                url=url,
                name=name,
                is_valid=False,
                error_message="Feed contains only generic promotional content"
            )

        # Try enclosure first (preferred method)
        enclosure = first_item.find('enclosure')
        if enclosure is not None:
            image_url = enclosure.get('url')
            if image_url and self._is_valid_image_url(image_url):
                print("✓ Valid (enclosure)")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=True,
                    comic_title=title,
                    image_url=image_url,
                    image_source='enclosure'
                )

        # Fallback: try to extract from description
        description = first_item.find('description')
        if description is not None and description.text:
            parser = ImageExtractor()
            parser.feed(description.text)

            if parser.image_url and self._is_valid_image_url(parser.image_url):
                print("✓ Valid (description)")
                return ValidationResult(
                    url=url,
                    name=name,
                    is_valid=True,
                    comic_title=title,
                    image_url=parser.image_url,
                    image_source='description'
                )

        # No valid image found
        print(f"❌ No valid image - {url}")
        return ValidationResult(
            url=url,
            name=name,
            is_valid=False,
            error_message="No valid image found in enclosure or description"
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

def _is_generic_promo(self, item, title: str) -> bool:
    """Check if this is generic promotional content rather than a comic strip"""
    # Check for generic promotional keywords in title
    generic_title_keywords = [
        "read", "explore the archive", "dive into", "check out",
        "by creator", "on gocomics", "comic strip by creator"
    ]
    
    title_lower = title.lower() if title else ""
    if any(keyword in title_lower for keyword in generic_title_keywords):
        return True
    
    # Check if the link just goes to the main comic page (not a specific strip)
    link = item.find('link')
    if link is not None and link.text:
        link_text = link.text.lower()
        # If link doesn't have a date pattern or specific strip identifier
        if not any(char.isdigit() for char in link_text.split('/')[-1]):
            return True
    
    # Check description for generic promotional text
    description = item.find('description')
    if description is not None and description.text:
        desc_lower = description.text.lower()
        promo_keywords = [
            "explore the archive", "dive into", "read extra content",
            "by creator", "generic_fb", "social_fb"
        ]
        if any(keyword in desc_lower for keyword in promo_keywords):
            return True
    
    # Check if image URL contains generic social media or promotional identifiers
    description = item.find('description')
    if description is not None and description.text:
        parser = ImageExtractor()
        parser.feed(description.text)
        if parser.image_url:
            url_lower = parser.image_url.lower()
            if any(keyword in url_lower for keyword in ['generic', 'social_fb', 'social_', 'og_image']):
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
        Validate multiple RSS feeds

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
                'status': 'needs_investigation'
            }
            report['failed_feeds'].append(feed_info)

        # Save to YAML
        with open(output_path, 'w') as f:
            yaml.dump(report, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"\n⚠️  Failed feeds report saved to: {output_path}")
        print(f"   {len(invalid_results)} feed(s) need investigation")
