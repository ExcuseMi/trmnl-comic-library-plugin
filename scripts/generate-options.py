from pathlib import Path
import os

import requests
import yaml
from dotenv import load_dotenv

from rss_feed_validator import RSSFeedValidator

URL = "https://comiccaster.xyz/comics_list.json"
URL_POLITICAL = "https://comiccaster.xyz/political_comics_list.json"

OTHER_LANGUAGES_KEYSWORDS: list[str] = [
    "en español",
    "espanol",
    "spanish"
]


def load_environment():
    """Load environment variables from plugins.env file"""
    current_dir = Path.cwd()

    # If we're in the scripts directory, look for plugins.env in the parent directory
    if current_dir.name == 'scripts':
        env_path = current_dir.parent / "plugins.env"
    else:
        # We're already in the repository root
        env_path = current_dir / "plugins.env"

    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from: {env_path}")
    else:
        print(f"plugins.env not found at {env_path}, using system environment variables")


def is_other_language(name: str, slug: str, author: str):
    if name:
        lower_name = name.lower()
        slug_lower = slug.lower()
        author_lower = author.lower() if author else ""

        for keyword in OTHER_LANGUAGES_KEYSWORDS:
            if keyword in lower_name or keyword in slug_lower or keyword in author_lower:
                return True
    return False


def get_excluded_feeds():
    """Get list of feeds to exclude from environment variable"""
    exclusions_str = os.environ.get('EXCLUSIONS', '')
    if exclusions_str:
        excluded_feeds = [url.strip() for url in exclusions_str.split(',') if url.strip()]
        print(f"Excluding {len(excluded_feeds)} feeds: {excluded_feeds}")
        return excluded_feeds
    return []


def get_comics_data(url: str):
    print("Fetching:", url)
    r = requests.get(url)
    r.raise_for_status()
    return r.json()


def get_extra_feeds_path():
    """Get the correct path for extra_feeds.yml that works from both root and scripts directory"""
    current_dir = Path.cwd()

    # If we're in the scripts directory, look for extra_feeds.yml in the parent directory
    if current_dir.name == 'scripts':
        return current_dir.parent / "extra_feeds.yml"
    else:
        # We're already in the repository root
        return current_dir / "extra_feeds.yml"


def load_extra_feeds():
    """Load additional RSS feeds from extra_feeds.yml"""
    extra_feeds_path = get_extra_feeds_path()
    if extra_feeds_path.exists():
        with open(extra_feeds_path, 'r') as f:
            extra_feeds = yaml.safe_load(f) or {}
        print(f"Loaded {len(extra_feeds)} extra feeds from {extra_feeds_path}")
        return extra_feeds
    else:
        print(f"extra_feeds.yml not found at {extra_feeds_path}, skipping extra feeds")
        return {}


def get_output_path():
    """Get the correct output path that works from both root and scripts directory"""
    current_dir = Path.cwd()

    # If we're in the scripts directory, go up one level to repository root
    if current_dir.name == 'scripts':
        return current_dir.parent / "updated_settings.yml"
    else:
        # We're already in the repository root
        return current_dir / "updated_settings.yml"


def get_failed_feeds_path():
    """Get the path for the failed feeds report - same directory as updated_settings.yml"""
    output_path = get_output_path()
    return output_path.parent / "failed_feeds_report.yml"


def should_exclude_feed(feed_url: str, excluded_feeds: list) -> bool:
    """Check if a feed should be excluded based on the EXCLUSIONS list"""
    return feed_url in excluded_feeds


def create_updated_settings():
    # Load environment variables first
    load_environment()

    # Get excluded feeds from environment
    excluded_feeds = get_excluded_feeds()

    # Get the current comics data
    comics_data = get_comics_data(URL)
    political_data = get_comics_data(URL_POLITICAL)
    extra_feeds = load_extra_feeds()

    # Create a set of political comic slugs for efficient lookup
    political_slugs = {comic.get("slug") for comic in political_data if comic.get("slug")}
    print(f"\nFound {len(political_slugs)} political comics")

    # Prepare all feeds for validation
    print("\n" + "=" * 60)
    print("VALIDATING ALL RSS FEEDS")
    print("=" * 60)

    validator = RSSFeedValidator(timeout=15)
    all_invalid_results = []

    # Validate regular comics (excluding those that are political and excluded feeds)
    print("\n--- Regular Comics ---")
    regular_feeds = {}
    for comic in comics_data:
        name = comic.get("name", "Unknown")
        slug = comic.get("slug", None)
        author = comic.get("author", "")
        feed_url = f"https://comiccaster.xyz/rss/{slug}" if slug else None

        # Exclude comics that are political, in other languages, or in the exclusion list
        if slug and not is_other_language(name, slug, author) and slug not in political_slugs:
            if feed_url and not should_exclude_feed(feed_url, excluded_feeds):
                regular_feeds[name] = feed_url
            else:
                print(f"  Excluded: {name} ({feed_url})")

    regular_valid, regular_invalid = validator.validate_multiple_feeds(regular_feeds)
    all_invalid_results.extend(regular_invalid)

    # Validate other language comics (excluding those that are political and excluded feeds)
    print("\n--- Comics in Other Languages ---")
    other_lang_feeds = {}
    for comic in comics_data:
        name = comic.get("name", "Unknown")
        slug = comic.get("slug", None)
        author = comic.get("author", "")
        feed_url = f"https://comiccaster.xyz/rss/{slug}" if slug else None

        # Exclude comics that are political or in the exclusion list
        if slug and is_other_language(name, slug, author) and slug not in political_slugs:
            if feed_url and not should_exclude_feed(feed_url, excluded_feeds):
                other_lang_feeds[name] = feed_url
            else:
                print(f"  Excluded: {name} ({feed_url})")

    other_lang_valid, other_lang_invalid = validator.validate_multiple_feeds(other_lang_feeds)
    all_invalid_results.extend(other_lang_invalid)

    # Validate political comics (excluding excluded feeds)
    print("\n--- Political Comics ---")
    political_feeds = {}
    for comic in political_data:
        name = comic.get("name", "Unknown")
        slug = comic.get("slug", None)
        feed_url = f"https://comiccaster.xyz/rss/{slug}" if slug else None

        if slug:
            if feed_url and not should_exclude_feed(feed_url, excluded_feeds):
                political_feeds[name] = feed_url
            else:
                print(f"  Excluded: {name} ({feed_url})")

    political_valid, political_invalid = validator.validate_multiple_feeds(political_feeds)
    all_invalid_results.extend(political_invalid)

    # Validate extra feeds (excluding excluded feeds)
    validated_extra_feeds = {}
    if extra_feeds:
        print("\n--- Extra Feeds ---")
        # Filter out excluded extra feeds
        filtered_extra_feeds = {}
        for name, url in extra_feeds.items():
            if not should_exclude_feed(url, excluded_feeds):
                filtered_extra_feeds[name] = url
            else:
                print(f"  Excluded: {name} ({url})")

        extra_valid, extra_invalid = validator.validate_multiple_feeds(filtered_extra_feeds)
        all_invalid_results.extend(extra_invalid)
        validated_extra_feeds = {result.name: result.url for result in extra_valid}
    else:
        print("\n--- Extra Feeds ---")
        print("No extra feeds to validate")

    # Print overall validation summary
    total_valid = len(regular_valid) + len(other_lang_valid) + len(political_valid) + len(validated_extra_feeds)
    total_invalid = len(all_invalid_results)
    print(f"\n{'=' * 60}")
    print(f"OVERALL VALIDATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total feeds validated: {total_valid + total_invalid}")
    print(f"✓ Valid: {total_valid} ({total_valid / (total_valid + total_invalid) * 100:.1f}%)")
    print(f"✗ Invalid: {total_invalid} ({total_invalid / (total_valid + total_invalid) * 100:.1f}%)")

    # Save failed feeds report
    validator.save_failed_feeds_report(all_invalid_results, get_failed_feeds_path())

    # Separate regular comics from other languages (only valid ones, excluding political)
    regular_comics = []
    other_language_comics = []

    # Use only validated comics
    valid_regular_names = {result.name for result in regular_valid}
    valid_other_lang_names = {result.name for result in other_lang_valid}

    for comic in comics_data:
        name = comic.get("name", "Unknown")
        slug = comic.get("slug", None)
        feed_url = f"https://comiccaster.xyz/rss/{slug}" if slug else None

        # Only include if not political and not excluded
        if slug not in political_slugs and feed_url and not should_exclude_feed(feed_url, excluded_feeds):
            if name in valid_regular_names:
                regular_comics.append(comic)
            elif name in valid_other_lang_names:
                other_language_comics.append(comic)

    # Filter political comics to only valid ones and not excluded
    valid_political_names = {result.name for result in political_valid}
    political_data = [comic for comic in political_data if comic.get("name") in valid_political_names]

    # Count totals for the description (all unique entries)
    total_regular = len(regular_comics)
    total_other_lang = len(other_language_comics)
    total_political = len(political_data)
    total_extra = len(validated_extra_feeds)
    total_all = total_regular + total_other_lang + total_political + total_extra

    # Create the updated custom fields
    custom_fields = []

    # About field with updated count
    about_field = {
        'keyname': 'about',
        'name': 'About This Plugin',
        'field_type': 'author_bio',
        'description': f"Access a collection of {total_all} comic RSS feeds and enjoy fresh content every day.<br /><br />\n<strong>Features:</strong><br />\n"
                       f"● Displays the most recent comic or a random comic<br />\n"
                       f"● Supports multiple RSS sources<br />\n"
                       f"● Add your own RSS feeds<br />\n"
                       f"● Frequently updated to keep all RSS sources valid and up to date"
        ,
        'github_url': 'https://github.com/ExcuseMi/trmnl-more-comics-plugin',
        'learn_more_url': 'https://comiccaster.xyz',
        'category': 'comics'
    }
    custom_fields.append(about_field)

    # Comics field - sort by name
    comics_options = []
    for comic in sorted(regular_comics, key=lambda x: x.get("name", "Unknown").lower()):
        name = comic.get("name", "Unknown")
        author = comic.get("author", "")
        slug = comic.get("slug", None)
        if slug:
            display_name = f"{name} by {author}" if author and author != name else name
            comics_options.append({display_name: f"https://comiccaster.xyz/rss/{slug}"})

    # Add validated extra feeds to comics options
    for name, url in validated_extra_feeds.items():
        comics_options.append({name: url})

    # Sort all comics options by name (case insensitive)
    comics_options.sort(key=lambda x: list(x.keys())[0].lower())

    comics_field = {
        'keyname': 'comics',
        'field_type': 'select',
        'name': f'Comics: {len(comics_options)}',
        'multiple': True,
        'help_text': 'Use <kbd>⌘</kbd>+<kbd>click</kbd> (Mac) or <kbd>ctrl</kbd>+<kbd>click</kbd> (Windows) to select multiple items. Use <kbd>Shift</kbd>+<kbd>click</kbd> to select a whole range at once.',
        'optional': True,
        'options': comics_options
    }
    custom_fields.append(comics_field)

    # Comics other languages field - sort by name
    other_lang_options = []
    for comic in sorted(other_language_comics, key=lambda x: x.get("name", "Unknown").lower()):
        name = comic.get("name", "Unknown")
        author = comic.get("author", "")
        slug = comic.get("slug", "unknown")
        display_name = f"{name} by {author}" if author and author != name else name
        other_lang_options.append({display_name: slug})

    other_lang_field = {
        'keyname': 'comics_other_languages',
        'field_type': 'select',
        'name': f'Comics in other languages: {len(other_lang_options)}',
        'multiple': True,
        'help_text': 'Use <kbd>⌘</kbd>+<kbd>click</kbd> (Mac) or <kbd>ctrl</kbd>+<kbd>click</kbd> (Windows) to select multiple items. Use <kbd>Shift</kbd>+<kbd>click</kbd> to select a whole range at once.',
        'optional': True,
        'options': other_lang_options
    }
    custom_fields.append(other_lang_field)

    # Political comics field - sort by name
    political_options = []
    for comic in sorted(political_data, key=lambda x: x.get("name", "Unknown").lower()):
        name = comic.get("name", "Unknown")
        author = comic.get("author", "")
        slug = comic.get("slug", "unknown")
        display_name = f"{name} by {author}" if author and author != name else name
        political_options.append({display_name: slug})

    political_field = {
        'keyname': 'comics_political',
        'field_type': 'select',
        'name': f'Political Comics: {len(political_options)}',
        'multiple': True,
        'help_text': 'Use <kbd>⌘</kbd>+<kbd>click</kbd> (Mac) or <kbd>ctrl</kbd>+<kbd>click</kbd> (Windows) to select multiple items. Use <kbd>Shift</kbd>+<kbd>click</kbd> to select a whole range at once.',
        'optional': True,
        'options': political_options
    }
    custom_fields.append(political_field)

    # Only show latest field
    only_latest_field = {
        'keyname': 'only_show_latest',
        'field_type': 'select',
        'name': 'Latest Comic Only',
        'description': 'Show only the most recent comic from each RSS feed.',
        'options': ['Yes', 'No'],
        'default': 'No',
        'optional': True
    }
    custom_fields.append(only_latest_field)
    extra_rss_feeds = {
        'keyname': 'extra_rss_feeds',
        'field_type': 'multi_string',
        'name': 'Extra RSS Feeds',
        'description': "List of extra rss feeds.<br />Any RSS URL added here will be added as a                                         source.",
        'placeholder': 'https://rssfeed.com'
    }
    custom_fields.append(extra_rss_feeds)
    image_filter = {
        'keyname': 'image_filter',
        'field_type': 'select',
        'name': 'Image Filter',
        'description': 'Apply an image filter to alter the appearance on the device.',
        'options': [
            {"None": "none"},
            {"Standard": "brightness(0.9) contrast(1.3) saturate(0)"},
            {"Bold": "brightness(0.85) contrast(1.5) saturate(0)"},
            {"Subtle": "brightness(0.95) contrast(1.15) saturate(0)"},
            {"Crisp": "brightness(1.0) contrast(1.4) saturate(0)"},
            {"Dramatic": "brightness(0.8) contrast(1.6) saturate(0)"}
        ],
        'optional': True
    }
    custom_fields.append(image_filter)

    # Get the correct output path
    output_path = get_output_path()
    print(f"\nWriting to: {output_path.absolute()}")

    # Use the custom YAML representer to format the output properly
    def represent_dict_order(dumper, data):
        return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())

    yaml.add_representer(dict, represent_dict_order)

    with open(output_path, 'w') as f:
        yaml.dump(custom_fields, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=1000)

    print(f"✓ Successfully created {output_path}")

    # Print summary
    print(f"\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Regular comics: {total_regular}")
    print(f"Other language comics: {total_other_lang}")
    print(f"Political comics: {total_political}")
    print(f"Extra feeds (validated): {total_extra}")
    print(f"Total unique comics: {total_all}")


if __name__ == "__main__":
    create_updated_settings()