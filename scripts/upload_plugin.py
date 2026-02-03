#!/usr/bin/env python3
"""
upload_plugin.py

Zips plugin/ and uploads it to TRMNL.
Reads TRMNL_API_KEY from env, RECIPE_ID from plugins.env — same as sync.py.

Usage:
    export TRMNL_API_KEY='user_xxxxx'
    python scripts/upload_plugin.py
"""

import os
import sys
import zipfile
import requests
from pathlib import Path


# ---------------------------------------------------------------------------
# Colours  —  same as sync.py
# ---------------------------------------------------------------------------

class Colors:
    RED    = '\033[0;31m'
    GREEN  = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE   = '\033[0;36m'
    NC     = '\033[0m'


def log(message, color=None):
    print(f"{color}{message}{Colors.NC}" if color else message)


# ---------------------------------------------------------------------------
# Env helpers  —  same logic as sync.py
# ---------------------------------------------------------------------------

def load_env_file(env_path: Path) -> dict:
    """Parse plugins.env into a dict (ignores comments and blank lines)."""
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key] = value.strip('"\'')
    return env


def resolve_root() -> Path:
    here = Path.cwd()
    return here.parent if here.name == 'scripts' else here


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    root     = resolve_root()
    env_file = root / "plugins.env"
    plugin_dir = root / "plugin"

    log("\n=== TRMNL Plugin Upload ===\n", Colors.BLUE)

    # --- API key (environment) ---
    api_key = os.environ.get('TRMNL_API_KEY')
    if not api_key:
        log("✗ TRMNL_API_KEY not set", Colors.RED)
        log("  export TRMNL_API_KEY='user_xxxxx'")
        sys.exit(1)

    # --- plugins.env ---
    if not env_file.exists():
        log(f"✗ plugins.env not found at {env_file}", Colors.RED)
        sys.exit(1)

    env = load_env_file(env_file)
    recipe_id = env.get('RECIPE_ID')
    if not recipe_id:
        log("✗ RECIPE_ID not set in plugins.env", Colors.RED)
        sys.exit(1)

    # --- plugin/ sanity check ---
    if not plugin_dir.is_dir():
        log(f"✗ plugin/ directory not found at {plugin_dir}", Colors.RED)
        sys.exit(1)

    files = [f for f in plugin_dir.iterdir() if f.is_file()]
    if not files:
        log("✗ plugin/ is empty", Colors.RED)
        sys.exit(1)

    log(f"Packing {len(files)} file(s) from plugin/:", Colors.YELLOW)
    for f in sorted(files):
        print(f"  {f.name}")
    print()

    # --- zip ---
    zip_path = root / f"private_plugin_{recipe_id}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)

    log(f"✓ Created {zip_path.name} ({zip_path.stat().st_size} bytes)\n", Colors.GREEN)

    # --- upload ---
    log(f"Uploading to RECIPE {recipe_id}…", Colors.YELLOW)

    with open(zip_path, 'rb') as f:
        response = requests.post(
            f"https://usetrmnl.com/api/plugin_settings/{recipe_id}/archive",
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent":    "trmnl-upload-script",
            },
            files={'file': ('archive.zip', f, 'application/zip')},
        )

    # --- cleanup zip regardless of result ---
    zip_path.unlink()

    if response.status_code == 200:
        log("✓ Upload successful!\n", Colors.GREEN)
        log(f"  Dashboard: https://usetrmnl.com/plugin_settings/{recipe_id}/edit\n", Colors.GREEN)
    else:
        log(f"✗ Upload failed — HTTP {response.status_code}", Colors.RED)
        print(f"  {response.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()