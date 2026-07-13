---
name: design_skill_generator
description: "A tool and workflow package containing Python pipelines to crawl Next.js / Contentful-backed design system documentation sites, extract color/spacing tokens, download visual mockups, compile markdown reference guides, and package open-source fonts."
---

# Design System Generator Skill

You are equipped with a design system generation toolset that lets you parse design documentation portals (like `docs.wise.design` or other headless-CMS/NextJS platforms) and compile them into local, offline agent skills complete with visual asset catalogs, reference guides, and font archives.

---

## 1. Pipeline Execution Flow

The visual identity parser is composed of 4 modular Python scripts located in `scripts/`. To generate a new design system skill, run these modules sequentially:

### Step 1: Route Discovery & Metadata Crawling
Extracts the routing tree from the Next.js `__NEXT_DATA__` static JSON object and crawls all pages matching target category slugs, saving raw structural payloads locally.
```bash
python3 scripts/crawler.py [base_url] [section1,section2,...]
```
*   **Example:** `python3 scripts/crawler.py https://docs.wise.design/ foundations,components,patterns`
*   **Output:** Saves structural JSON data files into `raw_data/[category]/`.

### Step 2: Figma / S3 Media Download
Scans crawled page data for image nodes and S3 Figma renders, downloads them locally, and builds a mapping file (`url_to_assets_map.json`).
```bash
python3 scripts/download_assets.py [input_dir] [output_assets_dir] [mapping_file_json]
```
*   **Example:** `python3 scripts/download_assets.py raw_data skills/new_design/assets url_to_assets_map.json`
*   **Output:** Downloads files and saves matching configurations.

### Step 3: Markdown Compiling & Asset Linking
Walks through the category folders, parsing Rich Text blocks, paragraphs, and tables, and compiling them into offline reference guides. It automatically converts Figma image links to point to the local assets folder.
```bash
python3 scripts/compiler.py [category_name] [input_dir] [output_file] [assets_map_json]
```
*   **Example:** `python3 scripts/compiler.py components raw_data skills/new_design/references/components.md url_to_assets_map.json`
*   **Output:** Generates fully integrated, asset-linked markdown files.

### Step 4: Font Downloading & Extraction
Downloads the design system's open-source typeface weights (e.g., Inter) from public release archives or CDNs and extracts static weights directly to a fonts folder.
```bash
python3 scripts/download_fonts.py [zip_url] [output_dir] [filter1,filter2,...]
```
*   **Example:** `python3 scripts/download_fonts.py https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip skills/new_design/fonts Regular,Medium,SemiBold,Bold`
*   **Output:** Populates `fonts/` with TrueType/WOFF files.

---

## 2. Headless CMS / Contentful Parser Logic

When adapting these scripts for other design documentation portals:
1.  **JSON Structure:** Most portals use headless CMS APIs like Contentful. The text elements inside `crawler.py` are nested in node trees with key attributes `nodeType` (e.g., `paragraph`, `list-item`, `hyperlink`).
2.  **Tables:** Table rows are structured with arrays of `cells`. The compiler parses them into clean GitHub-flavored Markdown tables.
3.  **Image Maps:** S3 Figma CDN links expire over time. The compiler replaces remote links with relative static file references (`../assets/...`) to guarantee documentation persistence.
