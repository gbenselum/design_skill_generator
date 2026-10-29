#!/usr/bin/env python3
"""download_assets.py - download the images referenced by crawled page JSON.

Stage 2 of the pipeline. Scans every crawled page for image URLs, downloads them into a local
folder, and writes a mapping file so ``compiler.py`` can rewrite remote links to local paths.

This is what keeps a generated guide working after Figma and S3 links expire.

Standard library only. Python 3.9+.

CLI:
    python3 download_assets.py --config config.json
    python3 download_assets.py raw_data assets url_to_assets_map.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Content-type ids that hold an image, plus the nested reference list used by image groups.
DEFAULT_IMAGE_TYPES = ["figmaImage"]
DEFAULT_IMAGE_GROUP_TYPES = ["multipleFigmaImages"]

# Hosts and extensions that count as a direct image link.
IMAGE_HOST_HINTS = ("figma-alpha-api", "s3-alpha", "images.ctfassets.net", "figma.com/api")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif")


def content_type(block: Any) -> str | None:
    if not isinstance(block, dict):
        return None
    return block.get("sys", {}).get("contentType", {}).get("sys", {}).get("id")


def scan_for_images(
    obj: Any,
    image_types: list[str] | None = None,
    image_group_types: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return ``(url, alt)`` pairs found anywhere in a crawled payload."""
    image_types = image_types or DEFAULT_IMAGE_TYPES
    image_group_types = image_group_types or DEFAULT_IMAGE_GROUP_TYPES
    found: list[tuple[str, str]] = []

    def looks_like_image(value: str) -> bool:
        return any(hint in value for hint in IMAGE_HOST_HINTS) or (
            value.split("?")[0].lower().endswith(IMAGE_EXTENSIONS)
        )

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, str):
            # Some portals put an image URL in a plain string field.
            if looks_like_image(node):
                found.append((node, "Asset"))
            return
        if not isinstance(node, dict):
            return

        node_type = content_type(node)
        fields = node.get("fields", {}) or {}

        if node_type in image_types:
            url = fields.get("url")
            alt = fields.get("altText") or fields.get("figmaReference") or "Design asset"
            if url:
                found.append((url, alt))

        if node_type in image_group_types:
            for ref in fields.get("figmaReferences", []) or []:
                walk(ref)

        # Direct links, for portals that do not wrap images in a content type.
        url = node.get("url")
        if isinstance(url, str) and looks_like_image(url):
            found.append((url, node.get("altText") or node.get("title") or "Asset"))

        for value in node.values():
            walk(value)

    walk(obj)
    # De-duplicate while keeping the first alt text seen for each URL.
    seen: dict[str, str] = {}
    for url, alt in found:
        seen.setdefault(url, alt)
    return list(seen.items())


def extension_for(url: str) -> str:
    path = url.split("?")[0].lower()
    for ext in sorted(IMAGE_EXTENSIONS, key=len, reverse=True):
        if path.endswith(ext):
            return ext
    return ".png"


def safe_name(value: str, limit: int = 30) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return cleaned[:limit] or "asset"


def run_downloader(
    input_dir: str,
    output_dir: str,
    mapping_path: str,
    image_types: list[str] | None = None,
    image_group_types: list[str] | None = None,
    delay: float = 0.1,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 30.0,
) -> dict[str, str]:
    """Download every image under ``input_dir``. Returns the URL -> file name map."""
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    os.makedirs(output_dir, exist_ok=True)
    url_to_local: dict[str, str] = {}
    index = 1

    for category in sorted(os.listdir(input_dir)):
        category_path = os.path.join(input_dir, category)
        if not os.path.isdir(category_path):
            continue

        for filename in sorted(os.listdir(category_path)):
            if not filename.endswith(".json"):
                continue

            with open(os.path.join(category_path, filename), "r", encoding="utf-8") as handle:
                try:
                    data = json.load(handle)
                except json.JSONDecodeError as exc:
                    print(f"Skipping {filename}: {exc}")
                    continue

            page_slug = filename[:-5]
            for url, alt in scan_for_images(data, image_types, image_group_types):
                if url in url_to_local:
                    continue

                ext = extension_for(url)
                image_name = f"{category}_{page_slug}_{safe_name(alt)}_{index}{ext}"
                local_path = os.path.join(output_dir, image_name)
                print(f"Downloading: {url} -> {image_name}")

                try:
                    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        with open(local_path, "wb") as out:
                            out.write(response.read())
                    url_to_local[url] = image_name
                    index += 1
                    time.sleep(delay)
                except urllib.error.HTTPError as exc:
                    print(f"HTTP error {exc.code} for {url}")
                except Exception as exc:  # noqa: BLE001 - one bad asset must not stop the run
                    print(f"Failed to download {url}: {exc}")

    parent = os.path.dirname(mapping_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(mapping_path, "w", encoding="utf-8") as handle:
        json.dump(url_to_local, handle, indent=2)

    print(f"Download finished. {len(url_to_local)} asset(s) saved in {output_dir}.")
    return url_to_local


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download_assets.py",
        description="Stage 2: download images found in crawled page JSON.",
        epilog="Example: download_assets.py raw_data assets url_to_assets_map.json",
    )
    parser.add_argument("input_dir", nargs="?", default="raw_data", help="crawler output directory")
    parser.add_argument("output_dir", nargs="?", default="assets", help="where to save images")
    parser.add_argument("mapping_path", nargs="?", default="url_to_assets_map.json",
                        help="JSON map of remote URL to local file name")
    parser.add_argument("--config", help="JSON config file; overrides the positional arguments")
    parser.add_argument("--image-type", action="append", dest="image_types",
                        help="content-type id that holds an image; repeatable")
    parser.add_argument("--image-group-type", action="append", dest="image_group_types",
                        help="content-type id that holds a list of image references; repeatable")
    parser.add_argument("--delay", type=float, default=0.1, help="seconds between downloads")
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    output_cfg: dict = {}
    image_types = args.image_types
    image_group_types = args.image_group_types
    input_dir = args.input_dir
    output_dir = args.output_dir
    mapping_path = args.mapping_path

    if args.config:
        with open(args.config, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        output_cfg = config.get("output") or {}
        content_cfg = config.get("content_types") or {}
        image_types = image_types or content_cfg.get("image")
        image_group_types = image_group_types or content_cfg.get("image_group")
        input_dir = output_cfg.get("raw") or input_dir
        output_dir = output_cfg.get("assets") or output_dir
        mapping_path = output_cfg.get("asset_map") or mapping_path

    try:
        run_downloader(
            input_dir,
            output_dir,
            mapping_path,
            image_types,
            image_group_types,
            args.delay,
            timeout=args.timeout,
        )
    except FileNotFoundError as exc:
        print(exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
