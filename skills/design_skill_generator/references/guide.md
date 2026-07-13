# Design System Visual Identity Scraper & Compiler Guide

This guide outlines how to use and customize the Design System Generator scripts to extract, download, and build complete documentation modules from any web-based design system portal.

---

## 1. How the Parser Works Under the Hood

### Page Navigation & Route Discovery
Modern static design system documentation portals built on frameworks like Next.js store the state for the entire site (including routes, pages, and menus) inside an inline `<script>` tag with the identifier `__NEXT_DATA__`.
*   The script `scripts/crawler.py` requests pages and extracts this JSON tag using simple regular expressions.
*   Once extracted, it crawls down the nested list of child pages (under attributes like `pages` or `navigation`), matches paths that begin with your target sections (e.g. `components`, `foundations`), and queues them for downloading.

### Rich Text Node Mapping
CMS platforms like Contentful deliver text content as abstract syntax trees (AST) instead of raw HTML. For example:
```json
{
  "nodeType": "paragraph",
  "content": [
    {
      "nodeType": "text",
      "value": "This is a bold text",
      "marks": [{"type": "bold"}]
    }
  ]
}
```
The compiler script (`scripts/compiler.py`) walks this AST recursively:
*   `paragraph` blocks are appended with double line breaks (`\n\n`).
*   `text` items with marks of type `bold` are wrapped in `**`.
*   `list-item` nodes are converted into bullet points (`- `).
*   `heading-1` / `heading-2` headers are mapped to `#` and `##` titles.

---

## 2. Best Practices & Troubleshooting

### Rate Limits & Headers
Many enterprise documentation portals (like Wise, Shopify Polaris, or Salesforce Lightning) utilize firewalls or rate-limiters (e.g., Cloudflare).
*   Ensure that the `HEADERS` dictionary in `crawler.py` mimics a modern browser `User-Agent`.
*   If you receive HTTP `429` (Too Many Requests), increase the delay interval (`time.sleep(0.5)`) in the download loop.

### Remote Image Caching
Images in design documentation are often embedded as direct Figma frames, which use signed AWS S3 URLs. These signatures expire, rendering documentation images broken after a few hours/days.
*   Always run `download_assets.py` immediately after scraping.
*   This downloader copies the binary files locally and writes a persistent JSON lookup map (`url_to_assets_map.json`).
*   Running `compiler.py` will replace the ephemeral S3 links with stable local links (e.g., `../assets/my_image.png`).
