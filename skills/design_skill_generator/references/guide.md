# Parser internals and extension points

Companion to the README. Read this when a portal does not fit the defaults, or when a block type
needs real structure instead of a text fallback.

## The `__NEXT_DATA__` payload

A server-rendered Next.js page ships its state as JSON:

```html
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{...}}}</script>
```

`crawler.py` extracts that block with one regular expression and parses it with `json`. That is
the whole "scraping" step: no headless browser, no DOM library, no JavaScript execution.

Two paths matter:

| Path | Holds |
| --- | --- |
| `props.pageProps.pages` or `props.pageProps.navigation` | The route tree |
| `props.pageProps.page` | The body of the current page |

Both are configurable (`navigation_paths`, `content_paths`) because portals nest them differently.
The crawler tries each path in order and uses the first that resolves.

## Route discovery

The route tree is a nested list. Each node has a `slug` or a `uri`, and often a `pages` or
`children` list:

```json
{"slug": "components", "pages": [
  {"slug": "components/button"},
  {"slug": "components/select"}
]}
```

`extract_slugs()` walks the tree recursively, keeps every slug that starts with one of the
requested sections, and de-duplicates. The folder is the first path segment; the rest becomes the
file name, so `components/form/field` is written to
`raw_data/components/form-field.json`.

## Rich Text nodes

Contentful sends text as an AST. The mapping in `compiler.py`:

| `nodeType` | Markdown |
| --- | --- |
| `text` | The value, with `bold`, `italic`, `underline`, `code` marks applied |
| `paragraph` | The body, followed by a blank line |
| `list-item` | `- ` prefix |
| `unordered-list`, `ordered-list` | Children, plus a blank line |
| `heading-N` | `#` × (N + 2), so `heading-2` inside a section becomes `####` |
| `hyperlink`, `entry-hyperlink` | `[label](uri)` |
| `blockquote`, `quote` | `> ` prefix |
| `code-block` | Fenced block |
| `hr` | `---` |

Marks are applied in a fixed order, so bold plus underline becomes `<u>**text**</u>`. Add a mark by
extending the `if` chain in `clean_text()`.

## Block roles

`compile_section()` walks `sections[].fields.blocks[]` and dispatches on the content-type id.
`type_role()` maps that id to a role, which decouples the renderer from the portal's naming:

| Role | Default content type | Renderer |
| --- | --- | --- |
| `image` | `figmaImage` | `![alt](../assets/file)` |
| `image_group` | `multipleFigmaImages` | Each nested reference |
| `table` | `table` | GitHub-flavoured Markdown table |
| `color_list` | `colorBlocks` | Colour table with light and dark hex plus token |
| `group` | `section` | Nested heading, then its own blocks |

Rename a content type without touching code by overriding `content_types` in `config.json`.

## Adding a real renderer for a new block

Example: a `doDont` block with two lists. First, map the type:

```json
"content_types": {
  "do_dont": ["doDont"]
}
```

Then add the branch. A role with an underscore or a new key both work, because
`render_block()` dispatches on the role string:

```python
if role == "do_dont":
    fields = block.get("fields", {}) or {}
    out = f"#### {fields.get('title', 'Do and do not')}\n\n"
    for label, key in (("Do", "dos"), ("Do not", "donts")):
        items = fields.get(key) or []
        if items:
            out += f"**{label}**\n\n"
            out += "".join(f"- {clean_text(item).strip()}\n" for item in items)
            out += "\n"
    return out
```

Add the role to `DEFAULT_TYPES` too, so it works without a config override. Until then, the block
renders as text with an `<!-- unhandled content type: doDont -->` marker, which is how you find the
work that is still missing.

## Images

`download_assets.py` finds images three ways:

1. A node whose content type is in `image` or `image_group`.
2. Any dict with a `url` whose host or extension looks like an image.
3. Any bare string that looks like an image URL.

`IMAGE_HOST_HINTS` and `IMAGE_EXTENSIONS` at the top of the file are the knobs. File names are
built as `<section>_<page>_<alt>_<n><ext>`, so a guide can reference them for years after the
original CDN link dies.

## Debugging an empty crawl

| Symptom | Cause | Fix |
| --- | --- | --- |
| "no `__NEXT_DATA__` block" | Client-rendered site, or not Next.js | Unsupported. Say so, do not fake it |
| "no navigation tree found" | Wrong `navigation_paths` | Inspect the payload, set the real path |
| "no routes matched" | Section names differ from the slugs | Read the top-level slugs and use those |
| Sections found, guides empty | Wrong `content_paths` | Point it at the node that holds `sections` |
| Images missing from guides | Stage 2 did not run, or the map file path differs | Rerun stage 2, then stage 3 |

## Politeness and caching

- `request_delay_seconds` defaults to 0.5 s between page requests, `asset_delay_seconds` to 0.1 s
  between downloads. Do not set them to zero against a site you do not own.
- Every response is cached in `cache/`, keyed by URL. A second run makes no network calls. Use
  `--force` after the source site changes.
- The cache makes a re-run cheap, which matters because the compile stage is the one you will
  iterate on.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

`tests/fixtures/site/` is a miniature Next.js portal served by a local HTTP server. Add a fixture
page before you add a feature: it is the cheapest way to keep the pipeline honest.
