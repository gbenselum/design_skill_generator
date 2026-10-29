# design_skill_generator

An agent skill and a set of Python scripts that turn a design system
documentation site into an offline reference pack: crawled page data,
downloaded images, compiled Markdown guides and open-source font files.

Python 3 standard library only. No `pip install`, no Playwright, no API keys.

## The problem

Design documentation lives on a live website. Agent sessions lose access to it,
Figma and S3 asset links expire, and a design system you copied by hand goes
stale in a week. This tool copies the content into your repository once, so an
agent can read it offline and keep using it.

## What it does

Four scripts run in a fixed order. Each one writes files that the next one
reads.

| Step | Script | Input | Output |
| --- | --- | --- | --- |
| 1. Crawl | `scripts/crawler.py` | Site URL + section names | `raw_data/<section>/*.json` |
| 2. Assets | `scripts/download_assets.py` | `raw_data/` | `assets/*` + `url_to_assets_map.json` |
| 3. Compile | `scripts/compiler.py` | `raw_data/` + asset map | Markdown reference guides |
| 4. Fonts | `scripts/download_fonts.py` | Font archive URL | `fonts/*.ttf`, `*.woff` |

**Step 1 — Route discovery and crawl.** Reads the Next.js `__NEXT_DATA__` JSON
block from the entry page, walks the navigation tree, and keeps routes that
start with the section names you pass (`foundations`, `components`, `patterns`,
and so on). Each page payload is saved as JSON under `raw_data/`.

**Step 2 — Asset download.** Recursively scans the crawled JSON for Contentful
`figmaImage` blocks and for direct Figma/S3/CDN image URLs. Files land in a
local assets folder and each URL is recorded in a mapping file.

**Step 3 — Markdown compile.** Converts Contentful Rich Text AST nodes
(paragraphs, lists, hyperlinks, bold and underline marks) into Markdown, maps
tables to GitHub-flavoured Markdown, and rewrites remote image links to the
local copies. The result is a reference guide that works with no network.

**Step 4 — Fonts.** Downloads a font release archive, extracts the archive, and
copies only the weights you name (for example `Regular,Medium,SemiBold,Bold`).

## Install

The skill is a directory with a `SKILL.md` instruction sheet and a `scripts/`
folder. Copy it into the skills directory of your agent, then point the agent at
the `SKILL.md`.

```bash
git clone https://github.com/gbenselum/design_skill_generator.git
cd design_skill_generator
```

For Claude Code style layouts:

```bash
cp -r skills/design_skill_generator ~/.claude/skills/design_skill_generator
```

For opencode style layouts:

```bash
mkdir -p ~/.agents/skills
cp -r skills/design_skill_generator ~/.agents/skills/design_skill_generator
```

## Use

Run the scripts from the skill directory. Every script prints usage when you
call it with no arguments.

### 1. Crawl a documentation site

```bash
python3 scripts/crawler.py https://docs.wise.design/ foundations,components,patterns
```

### 2. Download the images those pages reference

```bash
python3 scripts/download_assets.py raw_data skills/new_design/assets url_to_assets_map.json
```

### 3. Compile one Markdown guide per section

```bash
python3 scripts/compiler.py components raw_data \
  skills/new_design/references/components.md url_to_assets_map.json
```

### 4. Add the typeface

```bash
python3 scripts/download_fonts.py \
  https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip \
  skills/new_design/fonts Regular,Medium,SemiBold,Bold
```

The output is a new skill directory you can hand to an agent:

```text
skills/new_design/
├── SKILL.md              # what you write: when to use this design system
├── references/
│   ├── components.md     # compiled guides, one per section
│   └── foundations.md
├── assets/               # downloaded images, local copies
└── fonts/                # selected font weights
```

## Supported sites

The crawler reads server-rendered Next.js pages. The target site must:

- serve HTML that contains a `<script id="__NEXT_DATA__">` JSON block, and
- keep its page tree under `pageProps.pages` or `pageProps.navigation`.

Step 3 also expects Contentful-style Rich Text nodes (`nodeType`,
`content`, `marks`). Other headless CMS shapes work after you adjust the key
names in `compiler.py`. `references/guide.md` explains the node mapping in
detail, including how to retarget the scripts at a different portal.

The working example in `SKILL.md` is `docs.wise.design`.

## Behaviour and limits

- **Polite by default.** The crawler waits 0.5 s between requests and caches
  every response in `cache/`, so a second run hits no network.
- **No browser.** The scripts use `urllib` and `re` against the JSON payload.
  They do not run JavaScript, so a client-only rendered site yields nothing.
- **Expiring links.** Figma and S3 URLs die over time. The compiler rewrites
  them to local paths, but only if you ran step 2 with the same mapping file.
- **Text only.** Legends burned into images stay in the image. Read the
  downloaded asset for anything the docs show as a picture.
- **Respect the source.** The scripts copy someone else's documentation and
  typefaces. Check the site's terms and each font licence before you publish a
  generated pack.

## Repository layout

```text
.
└── skills/design_skill_generator/
    ├── SKILL.md                 # the instruction sheet an agent reads
    ├── references/guide.md      # how the parser works, how to adapt it
    └── scripts/
        ├── crawler.py           # route discovery + page JSON cache
        ├── download_assets.py   # Figma / S3 / CDN image download
        ├── compiler.py          # Rich Text AST -> Markdown
        └── download_fonts.py    # font archive -> selected weights
```

`cache/`, `raw_data/` and `temp_*` are build artefacts and stay out of git.

## License

No license file is present in this repository yet. Add one before you reuse the
code in another project.
