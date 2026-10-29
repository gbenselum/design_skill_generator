# design_skill_generator

Turn a design system documentation website into an offline reference pack an AI agent can read:
crawled page data, downloaded images, compiled Markdown guides, and the typeface.

One command. No API keys, no browser, no `pip install`. Python 3.9+ standard library only.

```bash
python3 scripts/generate.py --config config.json
```

## What it does

Design systems live on websites. An agent session cannot read them offline, Figma and S3 asset
links expire, and anything copied by hand is stale in a week. This tool copies the content into
your repository once and keeps it usable.

It produces a folder shaped like an agent skill:

```text
my-design-system/
├── SKILL.md              # you write this: when to use the design system
├── references/
│   ├── foundations.md    # compiled guides, one per section
│   ├── components.md
│   └── patterns.md
├── assets/               # local copies of the images the guide references
└── fonts/                # selected font weights
```

## How it works

Four stages. Each one writes files the next one reads, so you can run them alone or in a chain.

| Stage | Script | Input | Output |
| --- | --- | --- | --- |
| 1. Crawl | `scripts/crawler.py` | Site URL + section names | `raw_data/<section>/*.json` |
| 2. Assets | `scripts/download_assets.py` | `raw_data/` | `assets/*` + `url_to_assets_map.json` |
| 3. Compile | `scripts/compiler.py` | `raw_data/` + asset map | `references/<section>.md` |
| 4. Fonts *(optional)* | `scripts/download_fonts.py` | Font release zip | `fonts/*.ttf`, `*.woff2` |

`scripts/generate.py` runs all four from one config file. Every stage is also a normal CLI with
`--help`, and a module you can import.

**Why it works without a browser.** Next.js documentation portals ship the entire site state as
JSON inside a `<script id="__NEXT_DATA__">` block. The crawler reads that JSON, which is the same
data the page renders from, so there is no DOM to parse and no JavaScript to run.

## Quick start

```bash
git clone https://github.com/gbenselum/design_skill_generator.git
cd design_skill_generator/skills/design_skill_generator

cp config.example.json config.json
$EDITOR config.json          # set base_url and sections

python3 scripts/generate.py --config config.json --dry-run   # show the plan
python3 scripts/generate.py --config config.json
```

The dry run is worth the five seconds: it prints the resolved paths and the stages that will run,
before anything is fetched.

### Run one stage

```bash
# 1. crawl two sections
python3 scripts/crawler.py https://docs.wise.design/ foundations,components

# 2. download the images those pages reference
python3 scripts/download_assets.py raw_data assets url_to_assets_map.json

# 3. compile one guide
python3 scripts/compiler.py components raw_data references/components.md url_to_assets_map.json

# 4. add the typeface (optional)
python3 scripts/download_fonts.py \
  https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip \
  fonts Regular,Medium,SemiBold,Bold
```

## Configuration

All keys except `base_url` and `sections` are optional. See
[`config.example.json`](skills/design_skill_generator/config.example.json).

| Key | Default | What it does |
| --- | --- | --- |
| `base_url` | — | Site root. Required |
| `sections` | — | Section names to crawl, for example `["components", "foundations"]`. Required |
| `navigation_paths` | `props.pageProps.pages`, then three fallbacks | Dotted JSON paths to the route tree. First match wins |
| `content_paths` | `props.pageProps.page` | Dotted path to the page body |
| `content_types` | `image`, `image_group`, `table`, `color_list`, `group` | Maps content-type ids to rendering roles |
| `output.raw` / `assets` / `asset_map` / `references` | `raw_data` / `assets` / `url_to_assets_map.json` / `references` | Where each stage writes |
| `fonts.url` / `weights` / `output` | none / `[]` / `fonts` | Optional font stage. No URL means skip |
| `request_delay_seconds` | `0.5` | Politeness delay between page requests |
| `asset_delay_seconds` | `0.1` | Politeness delay between image downloads |
| `cache_dir` | `cache` | HTTP cache. A second run hits no network |

## Adapting it to another portal

The pipeline assumes **server-rendered Next.js + Contentful Rich Text**, which covers a large share
of public design systems. Three knobs cover most differences:

1. **The route tree moved?** Open the entry page source, find `__NEXT_DATA__`, and set
   `navigation_paths` to the dotted path that holds the page list.
2. **Different content-type names?** Remap them in `content_types`. A type you do not map is not
   lost: it renders as its title and body text, followed by an
   `<!-- unhandled content type: ... -->` marker.
3. **Images in a plain string field?** Already handled. The asset stage looks for known CDNs and
   image file extensions anywhere in the payload, not only under a `url` key.

What it deliberately does **not** do: render JavaScript, log in, or handle a site with no
`__NEXT_DATA__`. A client-rendered portal returns "no `__NEXT_DATA__` block" and stops, rather than
writing an empty guide.

## Tests

Fully offline. The fixture site is served by a real local HTTP server, so the crawler runs the same
code path as against a live portal.

```bash
cd skills/design_skill_generator
python3 -m unittest discover -s tests -v
```

22 tests cover route discovery, Rich Text conversion, tables, colour lists, unknown-block
fallback, asset download and mapping, font filtering, and the full pipeline end to end.

## Install as an agent skill

The generator is the tool. The skill is what an agent reads afterwards.

```bash
cp -r skills/design_skill_generator ~/.claude/skills/my-design-system
```

Then replace the `SKILL.md` inside it with one that says when an agent should use this particular
design system, and keep the generated `references/`, `assets/` and `fonts/` beside it.

## Repository layout

```text
skills/design_skill_generator/
├── SKILL.md                 the agent instruction sheet
├── config.example.json      copy to config.json
├── references/guide.md      how the parser works, and how to adapt it
├── scripts/
│   ├── generate.py          all four stages, from one config
│   ├── crawler.py           route discovery + page JSON cache
│   ├── download_assets.py   image download + URL map
│   ├── compiler.py          Rich Text AST -> Markdown
│   └── download_fonts.py    font archive -> selected weights
└── tests/
    ├── test_pipeline.py     22 offline tests
    └── fixtures/site/       a miniature Next.js portal
```

## Limits

- **Text only.** Legends baked into an image stay in the image. Read the downloaded asset.
- **Expiring links.** The compiler rewrites remote image links to local paths, but only if stage 2
  ran with the same map file.
- **Fonts by substring.** `Bold` also matches `SemiBold`. Use a longer filter, or none.
- **Someone else's content.** The tool copies a site's documentation and typefaces. Check the
  site's terms and each font licence before you publish a generated pack.

## License

GPL-3.0. See [LICENSE](LICENSE).

This is a strong copyleft licence: you may reuse, modify and redistribute this code, but a
derivative you distribute must also be GPL-3.0. If you need permissive reuse inside a closed
product, this licence does not allow it; ask about a different arrangement.
