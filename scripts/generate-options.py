import requests
import yaml

URL = "https://comiccaster.xyz/comics_list.json"
URL_POLICAL ="https://comiccaster.xyz/political_comics_list.json"
def is_other_language(name: str):
    if "en Español" in name:
        return True
    return False

def get_data(url: str):
    print("Fetching:", url)
    r = requests.get(url)
    r.raise_for_status()
    comics = r.json()

    # Convert to Terminal-style select options
    options = []
    slugs = []
    print("\n# --- YAML OPTIONS ---")
    comics_other_languages = []
    for c in comics:
        name = c.get("name", "Unknown")
        slug = c.get("slug", "unknown")
        if is_other_language(name):
            comics_other_languages.append(c)
        else:
            print(f"  - \"{name}\": {slug}")


    print("\n# --- OTHER LANGUAGES YAML OPTIONS ---")
    for c in comics_other_languages:
        name = c.get("name", "Unknown")
        slug = c.get("slug", "unknown")
        print(f"  - \"{name}\": {slug}")


if __name__ == "__main__":
    get_data(URL)
    #get_data(URL_POLICAL)
