---
name: design_skill_generator
description: "Generate an offline design-system skill from a documentation website: crawl a Next.js/Contentful portal, download its images and fonts, and compile Markdown reference guides an agent can read without network access. Use when the user wants to capture a design system, extract its tokens, colours, components or patterns, or build a local reference pack for a design system."
---

# Design System Generator Skill

You have a toolset that converts a live design-system documentation portal into an offline skill:
crawled page JSON, local images, compiled Markdown guides, and the typeface.

The working example in this repository targets `docs.wise.design`, a Next.js site backed by
Contentful. The same pipeline handles any portal that ships its state in a `__NEXT_DATA__` block.

---

## 1. Run the whole pipeline

```bash
cd skills/design_skill_generator
cp config.example.json config.json
# set base_url and sections

python3 scripts/generate.py --config config.json --dry-run
python3 scripts/generate.py --config config.json
```

Four stages, in order. Each writes files the next one reads.

| Stage | Script | Input | Output |
| --- | --- | --- | --- |
| 1. Crawl | `crawler.py` | `base_url` + `sections` | `raw_data/<section>/*.json` |
| 2. Assets | `download_assets.py` | `raw_data/` | `assets/*` + `url_to_assets_map.json` |
| 3. Compile | `compiler.py` | `raw_data/` + map | `references/<section>.md` |
| 4. Fonts | `download_fonts.py` | archive URL | `fonts/*` |

Skip a stage with `--skip assets`, `--skip fonts`, and so on.

## 2. Run one stage

```bash
python3 scripts/crawler.py https://docs.wise.design/ foundations,components,patterns
python3 scripts/download_assets.py raw_data assets url_to_assets_map.json
python3 scripts/compiler.py components raw_data references/components.md url_to_assets_map.json
python3 scripts/download_fonts.py https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip fonts Regular,Medium,SemiBold,Bold
```

Every script has `--help` and can also be imported as a module (`run_crawler`,
`run_downloader`, `compile_section`, `download_and_extract_fonts`).

## 3. How the parser works

**Route discovery.** Next.js stores the whole site state, including the route tree, inside
`<script id="__NEXT_DATA__" type="application/json">`. The crawler reads that JSON, walks the
navigation list, and keeps routes whose slug starts with a requested section. No browser and no
DOM parsing is involved.

**Payload unwrapping.** The page body is normally at `props.pageProps.page`. If that path is
missing, the crawler falls back to `pageProps`, then to the whole payload. Configure
`content_paths` when a portal differs.

**Rich Text to Markdown.** Contentful delivers text as an abstract syntax tree, not HTML.
`compiler.py` maps `paragraph`, `list-item`, ordered and unordered lists, `heading-N`, `hyperlink`,
bold, italic, underline and code marks, tables, and colour palette blocks.

**Unknown blocks.** A content type the compiler does not recognise is rendered as its title and
body text, plus an `<!-- unhandled content type: ... -->` marker. Nothing is dropped silently.

**Images.** Figma and S3 URLs expire. Stage 2 downloads each one and writes a URL-to-file map.
Stage 3 rewrites those links to `../assets/<file>`, so the guide still works months later.

## 4. Adapting to a different portal

1. Check that the site is server-rendered. View source and search for `__NEXT_DATA__`. If it is
   absent, this tool cannot help: stop and say so.
2. Set `navigation_paths` to the dotted path that holds the page list.
3. Remap `content_types` if the portal uses different content-type ids.
4. Add a renderer in `compiler.py` if a block needs real structure, not just text. Add the role to
   `DEFAULT_TYPES` and a branch in `render_block()`.

`references/guide.md` covers the node mapping and the extension points in more detail.

## 5. Verify the output

- `references/<section>.md` exists and is not a stub.
- Every `![` in the guides points at a file that exists in `assets/`.
- `grep -c "unhandled content type" references/*.md` shows what still needs a renderer.
- The guides read correctly with the network off.

## 6. Finish the skill

The generator produces the content. It does not write the instruction sheet. Replace `SKILL.md`
with one that states when an agent should use this design system, which references to read for
which task, and which rules are non-negotiable for that brand.

## Rules

- Never invent a token, colour or component rule that is not in the crawled data.
- Never present a generated guide as the source of truth. The site is the source; the guide is a
  snapshot, with the crawl date.
- Respect the site's terms and each font licence before publishing a generated pack.
- Keep `cache/`, `raw_data/` and `temp_*` out of git. They are build artefacts.
