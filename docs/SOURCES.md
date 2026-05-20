# SOURCES.md — Adding and maintaining sources

How to add new manga sources without breaking the filter logic.

## Anatomy of an entry in `sources.yml`

Minimum:
```yaml
- name: "XX - Source Name"
  country: "Country Name"
  language: "Language Name"
  publisher: "Publisher Name"
  source_class: "official | retailer | trusted_media | social"
  kind: "html | rss | js | wiki"
  url: "https://example.com/manga/"
  enabled: true
  tags: ["manga", "official", "store"]
```

Optional:
```yaml
  purity: "manga_only" | "mixed"      # default manga_only
  selectors:
    item_selector: "li.product"        # CSS selector for cards
    title_selector: "a"                # selector inside the card
    description_selector: ".desc"      # optional
  max_pages: 5                         # 0 = use global default
  notes: "free-text"
  # For search-template entries:
  search_template: "https://example.com/search?q={query}"
  keywords:
    - "edicion coleccionista"
    - "deluxe"
    - "kanzenban"
```

## Recipe: add a new HTML retailer

1. **Inspect the site** with curl + BeautifulSoup. Find:
   - The container that wraps each product card.
   - The anchor with the product URL.
   - Where the title text lives (often inside that anchor).

   Common patterns:
   - **Shopify**: `li.grid__item` or `.product-card`, links to `/products/<handle>`.
   - **Tiendanube**: `[data-product-id]`, links to `/productos/<handle>`.
   - **Magento**: `li.product-item` or `.product`, links containing `/p/`.
   - **WooCommerce**: `li.product`, links to `/product/<handle>`.

2. **Add to sources.yml** with selectors:
   ```yaml
   - name: "AR - Example Editorial"
     country: "Argentina"
     language: "Español"
     publisher: "Example Editorial"
     source_class: "official"
     kind: "html"
     url: "https://example.com/manga"
     enabled: true
     tags: ["manga", "official", "store", "new-source"]
     selectors:
       item_selector: "[data-product-id]"
       title_selector: "a[href*='/productos/']"
     max_pages: 5
   ```

3. **Test selectively** without scraping everything:
   ```bash
   python scripts/manga_watch.py --only-tags new-source --dry-run
   ```

4. **Check the output** in `reports/YYYY-MM-DD.md`. If the candidates
   list looks right, drop `--dry-run`.

5. **Remove the `"new-source"` tag** once you're confident it's stable
   (or keep it for selective re-runs).

## Recipe: add a search-template entry

For retailers that don't have a clean "all manga" page but do have a
search that we can query for specific keywords.

```yaml
- name: "ES - Some Retailer (search)"
  country: "España"
  language: "Español"
  publisher: "Some Publisher"
  source_class: "retailer"
  kind: "html"
  enabled: true
  tags: ["manga", "retailer"]
  search_template: "https://some-retailer.com/search?q={query}"
  keywords:
    - "edicion coleccionista"
    - "deluxe"
    - "kanzenban"
    - "boxset"
```

`{query}` gets URL-encoded and substituted. Each keyword generates a
"virtual source" with name like `"ES - Some Retailer (search) [search: deluxe]"`.

**Watch out for mixed catalogs.** If the search returns non-manga
products (Hot Wheels, Marvel comics, sports cards, etc.), set
`purity: "mixed"` (see below).

## Recipe: when to use `purity: "mixed"`

A source is "mixed" if its catalog or feed includes things other than
manga. Behavior change:
- Pack-extras like "Collector's Edition" alone do NOT rescue an item.
- The default decision flips from "keep" to "discard". So you need a
  STRONG hint (manga / vol N / kanzenban / Deluxe Hardcover / Library
  Edition / etc.) to pass.

Examples already flagged:
- `US - Dark Horse Direct` (sells manga + comics + figures + statues +
  art prints + bookends).
- `MX - Panini Manga México` and its search variants (also sells trading
  cards, Hot Wheels, sports collectibles).
- `ES - Panini España (search)` (Marvel/DC comics, LIGA ESTE cromos).
- `ES - Norma (search)` (returns podcast episodes too).
- `US - Anime News Network News RSS` (news, not products).
- `US - ComicBook.com Anime` (blog).
- `US - Kodansha USA News` (blog with contests/announcements).
- `JP - Rakuten Books (search)` (encyclopedias, magazines, idol boxes).

**Test:** add the source, see if it lets through a non-manga item with
a pack-extras-only rescue (typical: a statue / figure / mug "Collector's
Edition"). If yes → mark mixed.

## Recipe: add a wiki parser

Wikis are sources that need custom Python parsing because their HTML
doesn't fit `extract_listing_candidates`. Examples: ListadoManga
(month-based calendar), Manga-Sanctuary (Unix timestamp planning),
Otaku Calendar, Manga México.

1. **Create the parser file** at `scripts/wikis/<name>.py`. Use
   `listadomanga.py` as the template. Implement the public API:
   ```python
   def parse_calendar_page(html_text, source_url) -> list[Candidate]
   def fetch_calendar_month(year, month, session, timeout) -> list[Candidate]
   def iter_year_months(yf, mf, yt, mt) -> list[tuple[int, int]]
   def bootstrap(yf, mf, yt, mt, session, sleep_seconds, timeout,
                 min_score, fetch_details) -> list[Candidate]
   ```

2. **Inside the parser:**
   - Each Candidate must be created via `candidate_from_source(source,
     title, url, description)` so the standard fields are populated.
   - Call `is_likely_manga(cand.title, cand.description, tags=cand.tags)`
     to filter out non-manga before adding to the result.
   - Call `score_candidate(cand)` to populate score / signals.
   - If items don't have unique URLs (e.g. a catalog wiki where all
     items share the catalog page URL), fabricate unique URLs with a
     query param like `?manga=publisher-slug`. Otherwise the
     URL-based dedup will collapse them.

3. **Register in `_run_wiki_bootstrap()`** (`scripts/manga_watch.py`):
   ```python
   elif args.bootstrap_wiki == "<name>":
       from wikis.<name> import bootstrap as wiki_bootstrap, iter_year_months
   ```
   Also add `"<name>"` to the `choices=` list of the
   `--bootstrap-wiki` argparse argument.

4. **Add a documental entry to `sources.yml`** so the source shows up in
   `--list-sources` and in the web filters. Marks `kind: "html"` (not
   `wiki`, since `wiki` is not a runtime kind) and `tags: ["wiki",
   "calendar", ...]`.

5. **Add tests** in `tests/test_extraction.py` covering at least:
   - Parsing happy path with a small realistic HTML.
   - Date parsing edge cases (if applicable).
   - URL uniqueness (if you fabricated synthetic URLs).

## Recipe: add a new metadata label

If a source uses a label that `_extract_label_value_pairs` doesn't
recognize (e.g. a new JP label, or a new way of saying "publisher"):

1. **Inspect the HTML** to confirm the label appears in a recognized
   structure (`<li><span>label</span>value</li>`, `<dt>/<dd>`,
   `<tr><th/td>label</th/td><td>value</td></tr>`).

2. **Add the label to `_FIELD_LABELS`** in `manga_watch.py`. It's a
   dict mapping field name to a tuple of label variants:
   ```python
   _FIELD_LABELS: dict[str, tuple[str, ...]] = {
       "author": (
           "dessinateur", "scénariste", "scenariste", "auteur", "auteurs",
           "autor", "autores", "author", "authors", "autore", "autori",
           "mangaka", "writer", "creator",
           "著者", "作者", "原作", "漫画",
           # ADD HERE
       ),
       ...
   }
   ```

3. **Add a test** in `tests/test_extraction.py` with the exact HTML
   snippet:
   ```python
   def test_extract_label_value_pairs_new_label():
       html = '<ul><li><span>NEW_LABEL</span>VALUE</li></ul>'
       soup = BeautifulSoup(html, "html.parser")
       pairs = mw._extract_label_value_pairs(soup)
       assert pairs.get("author") == "VALUE"
   ```

4. **Retrofit existing items** so the label gets applied historically:
   ```bash
   python scripts/retrofit/backfill_metadata.py --only author \
       --skip-source X --skip-source Y
   ```
   (Restrict to the source(s) you expect to benefit so the run is fast.)

## Recipe: when a source starts producing garbage

If after a re-scrape you see lots of new junk from one specific source:

1. **Look at 5-10 example titles** to spot the pattern. Use
   `grep -i "<source-name>" data/items.jsonl | head` or run
   `python scripts/retrofit/filter_non_manga.py --dry-run` and read the
   sample.

2. **Decide:** is the pattern site-wide non-manga (then mark `purity:
   mixed`) or is it a specific kind of product (then add a HARD/SOFT
   regex)?

3. **For new HARD/SOFT patterns:**
   - Add the regex to `_NON_MANGA_HARD` or `_NON_MANGA_SOFT` in
     `manga_watch.py`.
   - Write a unit test with the exact title.
   - Run `pytest` (should be green).
   - Run `scripts/retrofit/filter_non_manga.py` to clean historic data.

4. **For new STRONG patterns** (book formats that we want to KEEP in
   mixed sources):
   - Add to `_STRONG_MANGA_PATTERNS`.
   - Add a test with a borderline case (e.g. a Hellsing Deluxe Hardcover
     that should pass in Dark Horse Direct mixed source).
   - Run `pytest` and `filter_non_manga.py --dry-run` to ensure you
     didn't accidentally re-include too much.

## What NOT to add as a source

- **Aggregators that only link out without product metadata** (e.g.
  manganews.com news index — useful for spotting new products but
  produces shallow Candidates).
- **Marketplaces with too much noise** (general Amazon, eBay). Most
  results are imports / used books / non-manga.
- **Social media feeds without API access** (Twitter announcements,
  Instagram posts). Hard to scrape and don't add reliable structured
  data.

## Country / language labels

Stick to existing values for consistency in the web UI filters:

| Country (Spanish) | Language (Spanish) |
|---|---|
| Argentina | Español |
| España | Español |
| México | Español |
| España / LatAm | Español |
| Francia | Francés |
| Italia | Italiano |
| Japón | Japonés |
| Japón / Global | Japonés |
| Estados Unidos | Inglés |

If you genuinely need a new country, add it but mention in
`docs/SOURCES.md` and update the documentation table here.
