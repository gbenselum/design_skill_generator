#!/usr/bin/env python3
"""crawler.py - discover routes on a Next.js design-documentation site and cache the page JSON.

Stage 1 of the pipeline. Reads the inline ``__NEXT_DATA__`` block from the entry page, walks the
navigation tree, and saves the payload of every route that starts with one of the requested
sections.

Standard library only. Python 3.9+.

CLI:
    python3 crawler.py --config config.json
    python3 crawler.py https://docs.example.com/ foundations,components --output raw_data
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
from typing import Any, Iterable

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Where a Next.js portal keeps its route tree. The first path that resolves wins.
DEFAULT_NAV_PATHS = (
    "props.pageProps.pages",
    "props.pageProps.navigation",
    "pageProps.pages",
    "pageProps.navigation",
    "props.pages",
    "props.navigation",
)

# Where the page body lives inside the payload.
DEFAULT_CONTENT_PATHS = ("props.pageProps.page", "pageProps.page")

NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)


def resolve_path(obj: Any, dotted: str) -> Any:
    """Return the value at ``"a.b.c"`` in nested dicts, or None."""
    current = obj
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def cache_name(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", url) + ".json"


def fetch_page_data(
    url: str,
    cache_dir: str = "cache",
    delay: float = 0.5,
    user_agent: str = DEFAULT_USER_AGENT,
    force: bool = False,
) -> dict | None:
    """Fetch a page and return its ``__NEXT_DATA__`` payload. Uses a disk cache."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, cache_name(url))

    if os.path.exists(cache_path) and not force:
        try:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            # A corrupt cache entry must not stop the run.
            pass

    print(f"Fetching: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request) as response:
            html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code} for {url}")
        return None
    except Exception as exc:  # noqa: BLE001 - a bad page must not kill the crawl
        print(f"Error fetching {url}: {exc}")
        return None

    match = NEXT_DATA_PATTERN.search(html)
    if not match:
        print(f"Warning: no __NEXT_DATA__ block in {url}. Not a server-rendered Next.js page?")
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        print(f"Warning: __NEXT_DATA__ is not valid JSON in {url}: {exc}")
        return None

    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    time.sleep(delay)
    return data


def extract_slugs(navigation: Any, prefixes: Iterable[str]) -> list[str]:
    """Walk a nested page tree and return every slug that starts with a requested prefix."""
    prefixes = tuple(p.strip("/") for p in prefixes)
    found: list[str] = []

    def walk(items: Any) -> None:
        if not items:
            return
        if isinstance(items, dict):
            walk(items.get("pages") or items.get("children") or [])
            return
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = (item.get("slug") or item.get("uri") or "").strip("/")
            if slug and slug.startswith(prefixes) and slug not in found:
                found.append(slug)
            walk(item.get("pages") or item.get("children") or [])

    walk(navigation)
    return found


def pick_navigation(data: dict, nav_paths: Iterable[str]) -> Any:
    for path in nav_paths:
        value = resolve_path(data, path)
        if value:
            return value
    return None


def pick_content(data: dict, content_paths: Iterable[str]) -> Any:
    for path in content_paths:
        value = resolve_path(data, path)
        if value:
            return value
    return resolve_path(data, "props.pageProps") or data


def run_crawler(
    base_url: str,
    sections: Iterable[str],
    output_dir: str = "raw_data",
    cache_dir: str = "cache",
    nav_paths: Iterable[str] | None = None,
    content_paths: Iterable[str] | None = None,
    delay: float = 0.5,
    user_agent: str = DEFAULT_USER_AGENT,
    force: bool = False,
) -> list[str]:
    """Crawl every route in ``sections``. Returns the slugs that were written."""
    base_url = base_url.rstrip("/")
    sections = [s.strip() for s in sections if s.strip()]
    nav_paths = tuple(nav_paths or DEFAULT_NAV_PATHS)
    content_paths = tuple(content_paths or DEFAULT_CONTENT_PATHS)

    print(f"Starting crawl of {base_url} with sections: {sections}")
    home = fetch_page_data(base_url, cache_dir, delay, user_agent, force)
    if not home:
        print("Failed to fetch the entry page. Nothing to crawl.")
        return []

    navigation = pick_navigation(home, nav_paths)
    if not navigation:
        print("Warning: no navigation tree found at any of: " + ", ".join(nav_paths))
        print("Set navigation_paths in your config to the JSON path this site uses.")
        return []

    slugs = extract_slugs(navigation, sections)
    print(f"Found {len(slugs)} route(s) matching {sections}")
    if not slugs:
        print("No routes matched. Check the section names against the site navigation.")
        return []

    written: list[str] = []
    for slug in slugs:
        data = fetch_page_data(f"{base_url}/{slug}", cache_dir, delay, user_agent, force)
        if not data:
            continue

        page = pick_content(data, content_paths)
        category = next((p for p in sections if slug.startswith(p)), "general")

        category_dir = os.path.join(output_dir, category)
        os.makedirs(category_dir, exist_ok=True)

        relative = slug[len(category):].strip("/") if slug.startswith(category) else slug
        file_name = (relative or slug).replace("/", "-") + ".json"
        with open(os.path.join(category_dir, file_name), "w", encoding="utf-8") as handle:
            json.dump(page, handle, indent=2, ensure_ascii=False)
        written.append(slug)

    print(f"Crawl complete. {len(written)} page(s) written to {output_dir}.")
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawler.py",
        description="Stage 1: discover routes on a Next.js design-documentation site.",
        epilog="Example: crawler.py https://docs.wise.design/ foundations,components,patterns",
    )
    parser.add_argument("base_url", nargs="?", help="site root, for example https://docs.example.com/")
    parser.add_argument("sections", nargs="?", help="comma-separated section names, for example components,patterns")
    parser.add_argument("--config", help="JSON config file; overrides the positional arguments")
    parser.add_argument("--output", default="raw_data", help="where to write the page JSON (default: raw_data)")
    parser.add_argument("--cache", default="cache", help="HTTP cache directory (default: cache)")
    parser.add_argument("--nav-path", action="append", dest="nav_paths",
                        help="dotted JSON path to the route tree; repeatable")
    parser.add_argument("--content-path", action="append", dest="content_paths",
                        help="dotted JSON path to the page body; repeatable")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests (default: 0.5)")
    parser.add_argument("--force", action="store_true", help="ignore the cache and refetch")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config: dict = {}
    if args.config:
        with open(args.config, "r", encoding="utf-8") as handle:
            config = json.load(handle)

    base_url = config.get("base_url") or args.base_url
    sections = config.get("sections") or (args.sections.split(",") if args.sections else None)
    if not base_url or not sections:
        build_parser().print_help()
        return 2

    output = (config.get("output") or {}).get("raw") or args.output
    delay = config.get("request_delay_seconds", args.delay)

    run_crawler(
        base_url=base_url,
        sections=sections,
        output_dir=output,
        cache_dir=args.cache,
        nav_paths=args.nav_paths or config.get("navigation_paths"),
        content_paths=args.content_paths or config.get("content_paths"),
        delay=delay,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
