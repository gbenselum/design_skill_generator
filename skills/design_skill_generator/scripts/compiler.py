#!/usr/bin/env python3
"""compiler.py - turn crawled Contentful / Rich Text page JSON into Markdown guides.

Stage 3 of the pipeline. Reads the JSON written by ``crawler.py``, converts Rich Text AST nodes
to Markdown, renders tables and colour lists, rewrites image links to local assets, and writes one
guide per section.

Standard library only. Python 3.9+.

CLI:
    python3 compiler.py --config config.json
    python3 compiler.py components raw_data references/components.md url_to_assets_map.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Content-type ids this compiler knows how to render. Override them in config.json under
# "content_types" when a portal uses different names. Anything unlisted still gets rendered as
# text by render_unknown(), so no content is silently dropped.
DEFAULT_TYPES: dict[str, list[str]] = {
    "image": ["figmaImage"],
    "image_group": ["multipleFigmaImages"],
    "table": ["table"],
    "color_list": ["colorBlocks"],
    "group": ["section"],
}


# ------------------------------------------------------------------ helpers


def content_type(block: Any) -> str | None:
    """Return the Contentful content-type id of a block, if it has one."""
    if not isinstance(block, dict):
        return None
    return (
        block.get("sys", {})
        .get("contentType", {})
        .get("sys", {})
        .get("id")
    )


def type_role(block: Any, types: dict[str, list[str]]) -> str | None:
    """Map a block to a rendering role: image, image_group, table, color_list or group."""
    block_type = content_type(block)
    if not block_type:
        return None
    for role, names in types.items():
        if block_type in names:
            return role
    return None


def clean_text(text_obj: Any) -> str:
    """Convert Contentful Rich Text nodes to Markdown."""
    if not text_obj:
        return ""
    if isinstance(text_obj, str):
        return text_obj.strip()
    if isinstance(text_obj, list):
        return "".join(clean_text(item) for item in text_obj)
    if not isinstance(text_obj, dict):
        return str(text_obj)

    node_type = text_obj.get("nodeType", "")

    if node_type == "text":
        value = text_obj.get("value", "")
        marks = [m.get("type") for m in text_obj.get("marks", []) if isinstance(m, dict)]
        if "bold" in marks or "strong" in marks:
            value = f"**{value}**"
        if "italic" in marks:
            value = f"*{value}*"
        if "underline" in marks:
            value = f"<u>{value}</u>"
        if "code" in marks:
            value = f"`{value}`"
        return value

    if "hyperlink" in node_type or node_type in {"entry-hyperlink", "asset-hyperlink"}:
        uri = (text_obj.get("data") or {}).get("uri", "")
        label = "".join(clean_text(child) for child in text_obj.get("content", []))
        if uri:
            return f"[{label or uri}]({uri})"
        return label

    body = "".join(clean_text(child) for child in text_obj.get("content", []))

    if node_type == "paragraph":
        return body + "\n\n"
    if node_type == "list-item":
        return "- " + body.strip().replace("\n\n", "\n") + "\n"
    if node_type in {"unordered-list", "ordered-list"}:
        return body + "\n"
    if node_type in {"blockquote", "quote"}:
        return "> " + body.strip() + "\n\n"
    if node_type == "code-block":
        return "```\n" + body.strip() + "\n```\n\n"
    if node_type in {"hr", "horizontal-rule"}:
        return "\n---\n\n"
    if node_type.startswith("heading-"):
        try:
            level = int(node_type.rsplit("-", 1)[-1])
        except ValueError:
            level = 3
        return f"\n{'#' * (level + 2)} {body.strip()}\n\n"

    return body


def parse_table(table_block: Any, types: dict | None = None) -> str:
    """Render a Contentful table block as a GitHub-flavoured Markdown table."""
    if not table_block:
        return ""
    fields = table_block.get("fields", {}) or {}
    rows = fields.get("rows", []) or []
    if not rows:
        return ""

    def cells_of(row: dict) -> list[str]:
        return [
            clean_text((cell.get("fields", {}) or {}).get("body", "")).strip().replace("\n", "<br>")
            for cell in (row.get("fields", {}) or {}).get("cells", [])
        ]

    has_header = fields.get("hasHeader", True)
    if has_header:
        header_cells = cells_of(rows[0])
        start_row = 1
    else:
        header_cells = [f"Col {i + 1}" for i in range(len(cells_of(rows[0])))]
        start_row = 0

    if not header_cells:
        return ""

    markdown = "| " + " | ".join(header_cells) + " |\n"
    markdown += "| " + " | ".join(["---"] * len(header_cells)) + " |\n"

    for row in rows[start_row:]:
        cells = cells_of(row)
        if not cells:
            continue
        while len(cells) < len(header_cells):
            cells.append("")
        markdown += "| " + " | ".join(cells[: len(header_cells)]) + " |\n"

    return markdown


def render_image(block: Any, asset_map: dict, types: dict) -> str:
    """Render an image block as a local Markdown image reference."""
    if not block:
        return ""

    role = type_role(block, types)
    fields = block.get("fields", {}) or {}

    if role == "image":
        url = fields.get("url")
        alt = fields.get("altText") or fields.get("figmaReference") or "Design preview"
        local_name = asset_map.get(url)
        if local_name:
            return f"![{alt}](../assets/{local_name})\n\n"
        return ""

    if role == "image_group":
        return "".join(
            render_image(ref, asset_map, types)
            for ref in fields.get("figmaReferences", []) or []
        )

    return ""


def render_color_list(block: Any, types: dict) -> str:
    """Render a colour palette block as a table. Skips items marked as blank."""
    fields = block.get("fields", {}) or {}
    markdown = f"#### {fields.get('title', 'Colors')}\n\n"
    markdown += "| Color Name | Hex (Light) | Hex (Dark) | Token | Description |\n"
    markdown += "| --- | --- | --- | --- | --- |\n"
    for item in fields.get("colorBlockItems", []) or []:
        item_fields = item.get("fields", {}) or {}
        if item_fields.get("useAsBlank"):
            continue
        name = item_fields.get("colorName") or item_fields.get("captionTitle") or "Color"
        light = item_fields.get("hex", "")
        dark = item_fields.get("hexDarkMode", "")
        token = item_fields.get("backgroundToken") or item_fields.get("colorToken", "")
        description = (item_fields.get("captionBody", "") or "").replace("\n", "<br>")
        markdown += f"| {name} | `{light}` | `{dark}` | `{token}` | {description} |\n"
    return markdown + "\n"


def render_unknown(block: Any) -> str:
    """Render a block type we have no rule for, instead of dropping it.

    Design portals add content types over time. Silently losing a section is worse than an
    imperfect heading, so unknown blocks degrade to their readable text.
    """
    fields = block.get("fields", {}) or {}
    markdown = ""

    title = fields.get("title") or fields.get("heading") or fields.get("name")
    if isinstance(title, str) and title.strip():
        markdown += f"#### {title.strip()}\n\n"

    for key in ("subHeader", "content", "body", "text", "description", "captionBody"):
        value = fields.get(key)
        if not value:
            continue
        rendered = clean_text(value).strip()
        if rendered:
            markdown += rendered + "\n\n"

    if markdown:
        block_type = content_type(block) or "unknown"
        markdown += f"<!-- unhandled content type: {block_type} -->\n\n"
    return markdown


def render_block(block: Any, asset_map: dict, types: dict, depth: int = 0) -> str:
    """Dispatch one block to the right renderer."""
    if not block:
        return ""

    role = type_role(block, types)
    fields = block.get("fields", {}) or {}

    if role == "image":
        return render_image(block, asset_map, types)
    if role == "image_group":
        return render_image(block, asset_map, types)
    if role == "table":
        return parse_table(block, types) + "\n"
    if role == "color_list":
        return render_color_list(block, types)
    if role == "group":
        markdown = ""
        nested_title = fields.get("title")
        if nested_title:
            markdown += f"{'#' * min(depth + 4, 6)} {nested_title}\n\n"
        if fields.get("content"):
            markdown += clean_text(fields.get("content")) + "\n"
        for nested in fields.get("blocks", []) or []:
            markdown += render_block(nested, asset_map, types, depth + 1)
        return markdown

    # Unhandled: render the text, never drop it.
    return render_unknown(block)


def compile_section(
    category: str,
    input_dir: str,
    output_file: str,
    asset_map: dict | None = None,
    types: dict | None = None,
    title: str | None = None,
) -> str:
    """Compile one section folder into one Markdown file. Returns the Markdown."""
    asset_map = asset_map or {}
    types = types or DEFAULT_TYPES
    category_dir = os.path.join(input_dir, category)

    if not os.path.exists(category_dir):
        raise FileNotFoundError(f"Section folder not found: {category_dir}")

    heading = title or category.replace("-", " ").title()
    markdown = f"# Design System - {heading}\n\n"
    markdown += f"This guide covers the {category} references of the design system.\n\n"

    for filename in sorted(os.listdir(category_dir)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(category_dir, filename), "r", encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                print(f"Skipping {filename}: {exc}")
                continue

        page_title = data.get("title") or filename[:-5].replace("-", " ").title()
        markdown += f"## {page_title}\n\n"

        header = data.get("header")
        if isinstance(header, dict):
            header_fields = header.get("fields", {}) or {}
            if header_fields.get("subHeader"):
                markdown += clean_text(header_fields["subHeader"]) + "\n\n"
            if header_fields.get("image"):
                markdown += render_block(header_fields["image"], asset_map, types)

        for section in data.get("sections", []) or []:
            if not section:
                continue
            section_fields = section.get("fields", {}) or {}
            if section_fields.get("title"):
                markdown += f"### {section_fields['title']}\n\n"
            if section_fields.get("content"):
                markdown += clean_text(section_fields["content"]) + "\n\n"
            for block in section_fields.get("blocks", []) or []:
                markdown += render_block(block, asset_map, types, depth=1)

        markdown += "---\n\n"

    parent = os.path.dirname(output_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    print(f"Compiled {category} -> {output_file}")
    return markdown


# Backwards-compatible alias for the original function name.
compile_category = compile_section


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compiler.py",
        description="Stage 3: compile crawled page JSON into a Markdown guide.",
        epilog=(
            "Example: compiler.py components raw_data references/components.md "
            "url_to_assets_map.json"
        ),
    )
    parser.add_argument("category", nargs="?", help="section folder inside --input, for example components")
    parser.add_argument("input_dir", nargs="?", default="raw_data", help="crawler output directory")
    parser.add_argument("output_file", nargs="?", help="Markdown file to write")
    parser.add_argument("asset_map", nargs="?", help="JSON map of remote URL to local file name")
    parser.add_argument("--config", help="JSON config file; compiles every section it lists")
    parser.add_argument("--types", help="JSON file overriding content-type names")
    parser.add_argument("--title", help="heading for the guide (default: section name)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    types = dict(DEFAULT_TYPES)
    if args.types:
        with open(args.types, "r", encoding="utf-8") as handle:
            types.update(json.load(handle))

    config: dict = {}
    if args.config:
        with open(args.config, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        types.update(config.get("content_types") or {})

    output_cfg = config.get("output") or {}
    input_dir = output_cfg.get("raw") or args.input_dir
    asset_map_path = output_cfg.get("asset_map") or args.asset_map
    references_dir = output_cfg.get("references")
    sections = config.get("sections") or ([args.category] if args.category else [])

    asset_map: dict = {}
    if asset_map_path and os.path.exists(asset_map_path):
        with open(asset_map_path, "r", encoding="utf-8") as handle:
            asset_map = json.load(handle)

    if args.category and args.output_file:
        compile_section(args.category, input_dir, args.output_file, asset_map, types, args.title)
        return 0

    if not sections or not references_dir:
        build_parser().print_help()
        return 2

    for section in sections:
        if not os.path.isdir(os.path.join(input_dir, section)):
            print(f"Skipping {section}: nothing was crawled for it")
            continue
        compile_section(
            section,
            input_dir,
            os.path.join(references_dir, f"{section}.md"),
            asset_map,
            types,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
