#!/usr/bin/env python3
"""generate.py - run the whole pipeline from one config file.

Stages, in order:
  1. crawl    discover routes and cache page JSON
  2. assets   download the images those pages reference
  3. compile  turn the JSON into one Markdown guide per section
  4. fonts    extract selected font weights from a release archive (optional)

Standard library only. Python 3.9+.

CLI:
    python3 generate.py --config config.json
    python3 generate.py --config config.json --skip-fonts --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import compiler
import crawler
import download_assets
import download_fonts

STAGES = ("crawl", "assets", "compile", "fonts")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    for key in ("base_url", "sections"):
        if not config.get(key):
            raise SystemExit(f"config error: '{key}' is required in {path}")
    return config


def plan(config: dict, skip: set[str]) -> list[str]:
    steps = []
    for stage in STAGES:
        if stage in skip:
            continue
        if stage == "fonts" and not (config.get("fonts") or {}).get("url"):
            continue
        steps.append(stage)
    return steps


def run(config: dict, skip: set[str], force: bool, dry_run: bool) -> int:
    output_cfg = config.get("output") or {}
    raw_dir = output_cfg.get("raw") or "raw_data"
    assets_dir = output_cfg.get("assets") or "assets"
    asset_map = output_cfg.get("asset_map") or "url_to_assets_map.json"
    references_dir = output_cfg.get("references") or "references"

    steps = plan(config, skip)
    sections = [s.strip() for s in config["sections"] if s.strip()]

    print(f"Project : {config.get('name') or 'unnamed'}")
    print(f"Source  : {config['base_url']}")
    print(f"Sections: {', '.join(sections)}")
    print(f"Stages  : {' -> '.join(steps)}")
    print("")

    if dry_run:
        print("Dry run. Nothing was fetched or written.")
        print(f"Would crawl into {raw_dir}, assets into {assets_dir},")
        print(f"maps into {asset_map}, guides into {references_dir}.")
        return 0

    printed: list[str] = []

    if "crawl" in steps:
        slugs = crawler.run_crawler(
            base_url=config["base_url"],
            sections=sections,
            output_dir=raw_dir,
            cache_dir=config.get("cache_dir") or "cache",
            nav_paths=config.get("navigation_paths"),
            content_paths=config.get("content_paths"),
            delay=config.get("request_delay_seconds", 0.5),
            force=force,
        )
        if not slugs:
            print("Crawl produced nothing. Stopping before the later stages would compound the error.")
            return 1

    if "assets" in steps:
        content_cfg = config.get("content_types") or {}
        try:
            download_assets.run_downloader(
                raw_dir,
                assets_dir,
                asset_map,
                content_cfg.get("image"),
                content_cfg.get("image_group"),
                config.get("asset_delay_seconds", 0.1),
            )
        except FileNotFoundError as exc:
            print(f"Skipping assets: {exc}")

    if "compile" in steps:
        types = dict(compiler.DEFAULT_TYPES)
        types.update(config.get("content_types") or {})

        assets: dict = {}
        if os.path.exists(asset_map):
            with open(asset_map, "r", encoding="utf-8") as handle:
                assets = json.load(handle)

        os.makedirs(references_dir, exist_ok=True)
        for section in sections:
            if not os.path.isdir(os.path.join(raw_dir, section)):
                print(f"Skipping {section}: nothing was crawled for it")
                continue
            guide = os.path.join(references_dir, f"{section}.md")
            compiler.compile_section(section, raw_dir, guide, assets, types)
            printed.append(guide)

    if "fonts" in steps:
        fonts_cfg = config.get("fonts") or {}
        copied = download_fonts.download_and_extract_fonts(
            fonts_cfg["url"],
            fonts_cfg.get("output") or "fonts",
            fonts_cfg.get("weights") or [],
        )
        if copied:
            printed.append(fonts_cfg.get("output") or "fonts")

    print("")
    print("Done. Output:")
    for path in printed:
        print(f"  - {path}")
    if not printed:
        print("  (nothing written)")
    print("")
    print("Next: write SKILL.md for the new skill, describing when an agent should use this")
    print("design system, and keep the generated references/ folder beside it.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate.py",
        description="Run the full design-system extraction pipeline from one config file.",
        epilog="Example: generate.py --config config.json",
    )
    parser.add_argument("--config", default="config.json", help="path to the JSON config")
    parser.add_argument("--skip", action="append", choices=STAGES, default=[],
                        help="skip a stage; repeatable")
    parser.add_argument("--force", action="store_true", help="ignore the HTTP cache")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not os.path.exists(args.config):
        print(f"Config not found: {args.config}")
        print("Copy config.example.json to config.json and edit it.")
        return 2

    config = load_config(args.config)
    return run(config, set(args.skip), args.force, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
