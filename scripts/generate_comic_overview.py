"""
generate_comic_overview.py

Pure renderer. No network calls, no XML parsing.

Two modes:
  1. Called from generate-options.py  →  generate_overview(comics, output_path)
  2. Run standalone  →  python scripts/generate_comic_overview.py
     Optionally pass --json and --output to override paths.
"""

import json
import argparse
from pathlib import Path
from html import escape
from datetime import datetime


# ---------------------------------------------------------------------------
# Category config  —  badge colour per category
# ---------------------------------------------------------------------------

CATEGORY_COLOURS = {
    "Comics":          "#7c6aff",
    "Other Languages": "#4a9eff",
    "Political":       "#ff6a6a",
}

DEFAULT_COLOUR = "#7c6aff"


# ---------------------------------------------------------------------------
# Card + page rendering
# ---------------------------------------------------------------------------

def _render_card(comic: dict) -> str:
    name       = escape(comic.get("name") or "")
    author     = escape(comic.get("author") or "")
    title      = escape(comic.get("title") or name)
    category   = comic.get("category") or "Comics"
    cat_esc    = escape(category)
    image_url  = comic.get("image_url")
    caption    = comic.get("caption")
    link       = comic.get("link")
    error      = comic.get("error")

    if image_url:
        img_html = f'<img src="{escape(image_url)}" alt="{title}" loading="lazy">'
    else:
        img_html = '<div class="no-image">&#x1f5bc; No image</div>'

    col          = CATEGORY_COLOURS.get(category, DEFAULT_COLOUR)
    badge_html   = f'<span class="badge" style="background:{col}22; color:{col}; border-color:{col}44">{cat_esc}</span>'
    author_html  = f'<span class="author">by {author}</span>'                                                          if author  else ""
    caption_html = f'<p class="caption">"{escape(caption)}"</p>'                                                       if caption else ""
    link_html    = f'<a href="{escape(link)}" target="_blank" rel="noopener" class="read-link">Read &rarr;</a>'       if link    else ""
    error_html   = f'<div class="error-banner">{escape(error)}</div>'                                                   if error   else ""
    error_class  = " has-error" if error else ""

    return (
        f'<article class="card{error_class}" data-name="{name}" data-category="{cat_esc}">\n'
        f'  <div class="card-image">{img_html}</div>\n'
        f'  <div class="card-body">\n'
        f'    <h3 class="card-title">{title}</h3>\n'
        f'    <p class="card-meta">\n'
        f'      <span class="source">{name}</span>\n'
        f'      {author_html}\n'
        f'      {badge_html}\n'
        f'    </p>\n'
        f'    {caption_html}\n'
        f'    {link_html}\n'
        f'  </div>\n'
        f'  {error_html}\n'
        f'</article>\n'
    )


def _render_cat_button(cat: str) -> str:
    col = CATEGORY_COLOURS.get(cat, DEFAULT_COLOUR)
    return (
        f'  <button class="cat-btn" data-category="{escape(cat)}" '
        f'style="border-color:{col}44; color:{col}">&#x25cf; {escape(cat)}</button>'
    )

def _render_plugin_badge() -> str:
    """Render subtle plugin badge"""
    return '''
<div class="plugin-badge" style="
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: #1a1d27;
    border: 1px solid #2e3345;
    border-radius: 8px;
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    z-index: 1000;
    transition: all 0.3s;
" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 20px rgba(0, 0, 0, 0.4)';"
   onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 12px rgba(0, 0, 0, 0.3)';">
    <a href="https://trmnl.com/recipes/180935/install" 
       target="_blank" 
       rel="noopener noreferrer"
       style="
           color: #e2e4ea;
           text-decoration: none;
           display: flex;
           align-items: center;
           gap: 0.5rem;
       ">
        <span style="color: #7c6aff;">⚡</span>
        <span>Get Plugin</span>
    </a>
</div>
'''

def _render_page(comics: list[dict]) -> str:
    cards = "\n".join(_render_card(c) for c in comics)
    total = len(comics)
    ok    = sum(1 for c in comics if "error" not in c)
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")

    # only show buttons for categories that actually exist in the data
    present_cats = [cat for cat in ["Comics", "Other Languages", "Political"]
                        if any(c.get("category") == cat for c in comics)]
    cat_buttons  = "\n".join(_render_cat_button(cat) for cat in present_cats)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Comic Library &#x2014; Latest</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:         #0f1117;
    --surface:    #1a1d27;
    --surface-hi: #232736;
    --border:     #2e3345;
    --text:       #e2e4ea;
    --text-dim:   #7a7f95;
    --accent:     #7c6aff;
    --accent-hi:  #a394ff;
    --error-bg:   #2a1a1a;
    --error-text: #e07070;
    --radius:     12px;
  }}

  body {{
    font-family: "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    line-height: 1.5;
  }}

  /* ---- header ---- */
  header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 1.25rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem;
  }}
  header h1 {{
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--accent-hi);
    letter-spacing: -0.02em;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }}
  
  header h1 .logo {{
    width: 32px;
    height: 32px;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid var(--border);
  }}
  .header-meta {{ font-size: 0.82rem; color: var(--text-dim); }}

  /* ---- toolbar ---- */
  .toolbar {{
    padding: 1rem 2rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }}
  .toolbar input {{
    flex: 1 1 220px;
    max-width: 380px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    padding: 0.5rem 0.85rem;
    font-size: 0.9rem;
    outline: none;
  }}
  .toolbar input:focus          {{ border-color: var(--accent); }}
  .toolbar input::placeholder   {{ color: var(--text-dim); }}
  .toolbar select {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
  }}

  /* ---- category filter buttons ---- */
  .cat-btn {{
    background: transparent;
    border: 1px solid;
    border-radius: 20px;
    padding: 0.35rem 0.75rem;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .15s;
    white-space: nowrap;
  }}
  .cat-btn:hover            {{ opacity: 0.8; }}
  .cat-btn.active           {{ opacity: 1; }}
  .cat-btn:not(.active)     {{ opacity: 0.4; }}

  /* ---- grid ---- */
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1.25rem;
    padding: 0 2rem 3rem;
    max-width: 1400px;
    margin: 0 auto;
  }}

  /* ---- card ---- */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: border-color .2s, transform .15s;
  }}
  .card:hover              {{ border-color: var(--accent); transform: translateY(-2px); }}
  .card.has-error          {{ opacity: 0.6; }}

  .card-image {{
    width: 100%;
    aspect-ratio: 1 / 1;
    background: var(--surface-hi);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .card-image img          {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .card-image .no-image    {{ color: var(--text-dim); font-size: 0.85rem; }}

  .card-body {{
    padding: 0.85rem 1rem 1rem;
    display: flex;
    flex-direction: column;
    flex: 1;
    gap: 0.3rem;
  }}
  .card-title {{ font-size: 1rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .card-meta  {{ font-size: 0.78rem; color: var(--text-dim); display: flex; gap: 0.6rem; flex-wrap: wrap; align-items: center; }}
  .source     {{ font-weight: 600; color: var(--accent-hi); }}
  .author     {{ color: var(--text-dim); }}

  /* ---- badge (inside card) ---- */
  .badge {{
    display: inline-block;
    border: 1px solid;
    border-radius: 10px;
    padding: 0.1rem 0.5rem;
    font-size: 0.72rem;
    font-weight: 600;
    white-space: nowrap;
  }}

  .caption    {{ font-size: 0.82rem; color: var(--text-dim); font-style: italic; margin-top: auto; }}
  .read-link  {{ display: inline-block; margin-top: 0.5rem; font-size: 0.85rem; color: var(--accent-hi); text-decoration: none; font-weight: 600; }}
  .read-link:hover {{ color: #fff; }}

  .error-banner {{ background: var(--error-bg); color: var(--error-text); font-size: 0.78rem; padding: 0.4rem 1rem; text-align: center; }}

  @media (max-width: 600px) {{
    header, .toolbar {{ padding-left: 1rem; padding-right: 1rem; }}
    .grid {{ padding: 0 1rem 2rem; grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<header>
  <h1><img src="https://github.com/ExcuseMi/trmnl-comic-library-plugin/blob/main/assets/plugin-images/180935_icon.png?raw=true" class="logo" /> Comic Library</h1>
  <span class="header-meta">{ok} / {total} feeds loaded &middot; generated {now}</span>
</header>

<div class="toolbar">
  <input type="text" id="search" placeholder="Filter by title or source&#x2026;" autocomplete="off">
  <select id="sort">
    <option value="alpha-asc">A &rarr; Z</option>
    <option value="alpha-desc">Z &rarr; A</option>
    <option value="errors-last" selected>Errors last</option>
  </select>
{cat_buttons}
</div>

<div class="grid" id="grid">
{cards}
</div>

<script>
(function() {{
  const grid    = document.getElementById("grid");
  const search  = document.getElementById("search");
  const sort    = document.getElementById("sort");
  const catBtns = document.querySelectorAll(".cat-btn");
  const cards   = Array.from(grid.children);

  // start with all categories active
  const active = new Set(Array.from(catBtns).map(b => b.dataset.category));

  function syncBtnStyles() {{
    catBtns.forEach(b => b.classList.toggle("active", active.has(b.dataset.category)));
  }}

  function sortKey(card, mode) {{
    const name     = (card.dataset.name || "").toLowerCase();
    const hasError = card.classList.contains("has-error") ? "1" : "0";
    if (mode === "alpha-asc")   return name;
    if (mode === "alpha-desc")  return "\\uffff".repeat(40).slice(name.length) + name;
    /* errors-last */            return hasError + name;
  }}

  function render() {{
    const q    = search.value.toLowerCase();
    const mode = sort.value;

    const filtered = cards.filter(card => {{
      if (!active.has(card.dataset.category)) return false;
      if (q && !card.textContent.toLowerCase().includes(q)) return false;
      return true;
    }});

    filtered.sort((a, b) => sortKey(a, mode).localeCompare(sortKey(b, mode)));
    filtered.forEach(card => grid.appendChild(card));

    const visible = new Set(filtered);
    cards.forEach(card => {{ card.style.display = visible.has(card) ? "" : "none"; }});
  }}

  // category toggle: click once = isolate, click again = back to all
  catBtns.forEach(btn => {{
    btn.addEventListener("click", () => {{
      const cat = btn.dataset.category;

      if (active.size === 1 && active.has(cat)) {{
        // already isolated on this one — select all
        catBtns.forEach(b => active.add(b.dataset.category));
      }} else {{
        // isolate to just this category
        active.clear();
        active.add(cat);
      }}

      syncBtnStyles();
      render();
    }});
  }});

  search.addEventListener("input",  render);
  sort.addEventListener("change",   render);
  syncBtnStyles();
  render();
}})();
</script>
{_render_plugin_badge()}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public entry point  —  called from generate-options.py
# ---------------------------------------------------------------------------

def generate_overview(comics: list[dict], output_path: Path):
    """
    comics:      list of dicts  [{ name, author, title, image_url, link, caption, category }, …]
    output_path: where to write comic_overview.html
    """
    print(f"\n{'=' * 60}")
    print("GENERATING COMIC OVERVIEW")
    print(f"{'=' * 60}")

    ok = sum(1 for c in comics if "error" not in c)
    print(f"  {ok}/{len(comics)} comics have images")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(_render_page(comics))
    print(f"✓ Comic overview written: {output_path}")


# ---------------------------------------------------------------------------
# Standalone mode  —  python scripts/generate_comic_overview.py
# ---------------------------------------------------------------------------

def _resolve_base() -> Path:
    """Root of the repo, whether we're run from scripts/ or from root."""
    here = Path(__file__).resolve().parent
    return here.parent if here.name == "scripts" else here


if __name__ == "__main__":
    base = _resolve_base()

    parser = argparse.ArgumentParser(
        description="Re-render comic_overview.html from the cached JSON. "
                    "No network calls — just tweak the HTML and re-run."
    )
    parser.add_argument("--json",   type=Path, default=base / "data/comic_overview_data.json",
                        help="Path to the cached JSON (default: <repo>/comic_overview_data.json)")
    parser.add_argument("--output", type=Path, default=base / "index.html",
                        help="Output HTML path (default: <repo>/index.html)")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"[!] JSON cache not found: {args.json}")
        print("    Run generate-options.py first to create it.")
        raise SystemExit(1)

    with open(args.json, encoding="utf-8") as f:
        comics = json.load(f)

    print(f"[*] Loaded {len(comics)} comics from {args.json}")

    ok = sum(1 for c in comics if "error" not in c)
    print(f"  {ok}/{len(comics)} have images")

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(_render_page(comics))
    print(f"✓ Written: {args.output}")