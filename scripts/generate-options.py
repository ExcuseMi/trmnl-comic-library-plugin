import requests
import yaml
from pathlib import Path
import os

URL = "https://comiccaster.xyz/comics_list.json"
URL_POLITICAL = "https://comiccaster.xyz/political_comics_list.json"


def is_other_language(name: str):
    return "en Español" in name


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


def create_updated_settings():
    # Get the current comics data
    comics_data = get_comics_data(URL)
    political_data = get_comics_data(URL_POLITICAL)
    extra_feeds = load_extra_feeds()

    # Separate regular comics from other languages
    regular_comics = []
    other_language_comics = []

    for comic in comics_data:
        name = comic.get("name", "Unknown")
        if is_other_language(name):
            other_language_comics.append(comic)
        else:
            regular_comics.append(comic)

    # Count totals for the description
    total_regular = len(regular_comics)
    total_other_lang = len(other_language_comics)
    total_political = len(political_data)
    total_extra = len(extra_feeds)
    total_all = total_regular + total_other_lang + total_political + total_extra

    # Create the updated custom fields
    custom_fields = []

    # About field with updated count
    about_field = {
        'keyname': 'about',
        'name': 'About This Plugin',
        'field_type': 'author_bio',
        'description': f"Access a collection of {total_all} comic RSS feeds and enjoy fresh content every day.<br /><br />\n<strong>Features:</strong><br />\n● Displays the most recent comic or a random comic<br />\n● Supports multiple RSS sources",
        'github_url': 'https://github.com/ExcuseMi/trmnl-more-comics-plugin',
        'learn_more_url': 'https://comiccaster.xyz'
    }
    custom_fields.append(about_field)

    # Comics field - sort by name
    comics_options = []
    for comic in sorted(regular_comics, key=lambda x: x.get("name", "Unknown")):
        name = comic.get("name", "Unknown")
        slug = comic.get("slug", None)
        if slug:
            comics_options.append({name: f"https://comiccaster.xyz/rss/{slug}"})

    # Add extra feeds to comics options and sort everything
    for name, url in extra_feeds.items():
        comics_options.append({name: url})

    # Sort all comics options by name
    comics_options.sort(key=lambda x: list(x.keys())[0])

    comics_field = {
        'keyname': 'comics',
        'field_type': 'select',
        'name': 'Comics',
        'multiple': True,
        'help_text': 'Use <kbd>⌘</kbd>+<kbd>click</kbd> (Mac) or <kbd>ctrl</kbd>+<kbd>click</kbd> (Windows) to select multiple items. Use <kbd>Shift</kbd>+<kbd>click</kbd> to select a whole range at once.',
        'optional': True,
        'options': comics_options
    }
    custom_fields.append(comics_field)

    # Comics other languages field - sort by name
    other_lang_options = []
    for comic in sorted(other_language_comics, key=lambda x: x.get("name", "Unknown")):
        name = comic.get("name", "Unknown")
        slug = comic.get("slug", "unknown")
        other_lang_options.append({name: slug})

    other_lang_field = {
        'keyname': 'comics_other_languages',
        'field_type': 'select',
        'name': 'Comics in other languages',
        'multiple': True,
        'help_text': 'Use <kbd>⌘</kbd>+<kbd>click</kbd> (Mac) or <kbd>ctrl</kbd>+<kbd>click</kbd> (Windows) to select multiple items. Use <kbd>Shift</kbd>+<kbd>click</kbd> to select a whole range at once.',
        'optional': True,
        'options': other_lang_options
    }
    custom_fields.append(other_lang_field)

    # Political comics field - sort by name
    political_options = []
    for comic in sorted(political_data, key=lambda x: x.get("name", "Unknown")):
        name = comic.get("name", "Unknown")
        slug = comic.get("slug", "unknown")
        political_options.append({name: slug})

    political_field = {
        'keyname': 'comics_political',
        'field_type': 'select',
        'name': 'Political Comics',
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
        'description': "List of extra rss feeds.<br />Any RSS URL added here will be added as source.",
        'placeholder': 'https://rssfeed.com'
    }
    custom_fields.append(extra_rss_feeds)

    # Get the correct output path
    output_path = get_output_path()
    print(f"Writing to: {output_path.absolute()}")

    # Use the custom YAML representer to format the output properly
    def represent_dict_order(dumper, data):
        return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())

    yaml.add_representer(dict, represent_dict_order)

    with open(output_path, 'w') as f:
        yaml.dump(custom_fields, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=1000)

    print(f"Successfully created {output_path}")

    # Print summary
    print(f"\nSummary:")
    print(f"Regular comics: {total_regular}")
    print(f"Other language comics: {total_other_lang}")
    print(f"Political comics: {total_political}")
    print(f"Extra feeds: {total_extra}")
    print(f"Total comics: {total_all}")


if __name__ == "__main__":
    create_updated_settings()