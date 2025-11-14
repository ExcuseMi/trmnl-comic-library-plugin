import requests
import yaml

URL = "https://comiccaster.xyz/comics_list.json"
URL_POLICAL ="https://comiccaster.xyz/political_comics_list.json"

def get_data(url: str):
    print("Fetching:", url)
    r = requests.get(url)
    r.raise_for_status()
    comics = r.json()

    # Convert to Terminal-style select options
    options = []
    slugs = []
    print("\n# --- YAML OPTIONS ---")

    for c in comics:
        name = c.get("name", "Unknown")
        slug = c.get("slug", "unknown")
        print(f"  - \"{name}\": {slug}")
        slugs.append(slug)


    print("\n# --- SLUGS COMMA ---")
    print(",".join(slugs))



if __name__ == "__main__":
    #get_data(URL)
    get_data(URL_POLICAL)
