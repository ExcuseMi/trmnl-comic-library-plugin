#!/usr/bin/env python3
import requests
import re
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def load_plugin_config():
    """Load plugin IDs from plugins.env file"""
    config = {
        'plugin_ids': [],
        'section_title': '🚀 Plugin Statistics',
        'images_dir': 'assets/plugin-images'
    }

    try:
        with open('plugins.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        if key == 'PLUGIN_IDS':
                            config['plugin_ids'] = [pid.strip() for pid in value.split(',') if pid.strip()]
                        elif key == 'SECTION_TITLE':
                            config['section_title'] = value
                        elif key == 'IMAGES_DIR':
                            config['images_dir'] = value
    except FileNotFoundError:
        print("⚠️  plugins.env file not found. Using default configuration.")

    return config


def download_image(url: str, save_path: str):
    """Download an image from URL and save it locally"""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Save the image
        with open(save_path, 'wb') as f:
            f.write(response.content)

        print(f"  ✓ Downloaded: {os.path.basename(save_path)}")
        return True
    except requests.RequestException as e:
        print(f"  ✗ Failed to download image from {url}: {e}")
        return False


def get_image_extension(url: str):
    """Extract file extension from URL"""
    parsed = urlparse(url)
    path = parsed.path
    _, ext = os.path.splitext(path)
    # Default to .png if no extension found
    return ext if ext else '.png'


def fetch_plugin_data(plugin_id: str):
    """Fetch plugin data from TRMNL API"""
    url = f"https://usetrmnl.com/recipes/{plugin_id}.json"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"  ✗ Error fetching plugin data for {plugin_id}: {e}")
        return None


def process_plugin_images(plugin_id: str, plugin_data: dict, images_dir: str):
    """Download plugin images and return local paths"""
    if not plugin_data:
        return None, None

    plugin = plugin_data.get('data', {})

    # Get image URLs
    icon_url = plugin.get('icon_url', '')
    screenshot_url = plugin.get('screenshot_url', '')

    local_paths = {
        'icon': None,
        'screenshot': None
    }

    # Download icon
    if icon_url:
        icon_ext = get_image_extension(icon_url)
        icon_filename = f"{plugin_id}_icon{icon_ext}"
        icon_path = os.path.join(images_dir, icon_filename)

        if download_image(icon_url, icon_path):
            # Store relative path for README
            local_paths['icon'] = icon_path

    # Download screenshot
    if screenshot_url:
        screenshot_ext = get_image_extension(screenshot_url)
        screenshot_filename = f"{plugin_id}_screenshot{screenshot_ext}"
        screenshot_path = os.path.join(images_dir, screenshot_filename)

        if download_image(screenshot_url, screenshot_path):
            local_paths['screenshot'] = screenshot_path

    return local_paths


def generate_plugin_section(data, plugin_id: str, image_paths: dict):
    """Generate markdown section for a plugin"""
    if not data:
        return f"<!-- Plugin data unavailable for {plugin_id} -->"

    plugin = data.get('data', {})
    stats = plugin.get('stats', {})

    # Use local image paths or fallback to original URLs
    icon_path = image_paths.get('icon') if image_paths else plugin.get('icon_url', '')
    screenshot_path = image_paths.get('screenshot') if image_paths else plugin.get('screenshot_url', '')

    name = plugin.get('name', 'Unknown Plugin')
    description = plugin.get('author_bio', {}).get('description', 'No description available')
    installs = stats.get('installs', 0)
    forks = stats.get('forks', 0)

    markdown = f"""
## <img src="{icon_path}" alt="{name} icon" width="32"/> [{name}](https://usetrmnl.com/recipes/{plugin_id})

![{name} screenshot]({screenshot_path})

### Description
{description}

### 📊 Statistics

| Metric | Value |
|--------|-------|
| Installs | {installs:,} |
| Forks | {forks:,} |

---
"""
    return markdown


def update_readme(plugin_sections: str, section_title: str):
    """Update README.md with plugin statistics"""
    # Read existing README.md
    try:
        with open('README.md', 'r') as f:
            content = f.read()
    except FileNotFoundError:
        content = "# Project README\n\n"

    # Define markers for the plugin sections
    start_marker = "<!-- PLUGIN_STATS_START -->"
    end_marker = "<!-- PLUGIN_STATS_END -->"

    # Create the new plugin sections content
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    new_content = f"{start_marker}\n## {section_title}\n\n*Last updated: {timestamp}*\n\n{plugin_sections}\n{end_marker}"

    # Check if markers exist in the README
    if start_marker in content and end_marker in content:
        # Replace existing content between markers
        pattern = f"{re.escape(start_marker)}.*?{re.escape(end_marker)}"
        updated_content = re.sub(pattern, new_content, content, flags=re.DOTALL)
    else:
        # Append to the end of the README
        updated_content = content + "\n\n" + new_content + "\n"

    # Write updated content back to README.md
    with open('README.md', 'w') as f:
        f.write(updated_content)


def main():
    """Main execution function"""
    # Load configuration from plugins.env
    config = load_plugin_config()
    plugin_ids = config['plugin_ids']
    section_title = config['section_title']
    images_dir = config['images_dir']

    if not plugin_ids:
        print("❌ No plugin IDs found in plugins.env")
        return

    print(f"📋 Tracking {len(plugin_ids)} plugins: {', '.join(plugin_ids)}")
    print(f"📁 Images will be saved to: {images_dir}\n")

    plugin_sections = []
    total = len(plugin_ids)

    for idx, plugin_id in enumerate(plugin_ids, 1):
        print(f"🔍 [{idx}/{total}] Processing plugin: {plugin_id}")

        # Fetch plugin data
        data = fetch_plugin_data(plugin_id)

        # Download images
        image_paths = process_plugin_images(plugin_id, data, images_dir)

        # Generate markdown section
        section = generate_plugin_section(data, plugin_id, image_paths)
        plugin_sections.append(section)
        print()

    # Combine all sections
    all_sections = "\n".join(plugin_sections)

    # Update README
    update_readme(all_sections, section_title)

    print("✅ README.md updated successfully with plugin statistics!")
    print(f"📸 Images saved to: {images_dir}/")


if __name__ == "__main__":
    main()