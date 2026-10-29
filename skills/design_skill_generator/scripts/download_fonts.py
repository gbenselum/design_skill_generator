#!/usr/bin/env python3
"""download_fonts.py - fetch a font release archive and extract selected weights.

Stage 4 of the pipeline, and the only optional stage. Downloads a zip, extracts it to a temporary
directory, copies the weights you name, and cleans up.

Standard library only. Python 3.9+.

CLI:
    python3 download_fonts.py --config config.json
    python3 download_fonts.py https://example.com/Inter.zip fonts Regular,Medium,Bold
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from typing import Iterable

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

FONT_EXTENSIONS = (".ttf", ".otf", ".woff", ".woff2")


def download_and_extract_fonts(
    zip_url: str,
    output_dir: str,
    weights: Iterable[str] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 120.0,
) -> int:
    """Download ``zip_url`` and copy matching font files into ``output_dir``.

    ``weights`` matches case-insensitively against file names, for example
    ``["Regular", "SemiBold"]``. An empty filter copies every font in the archive.
    """
    os.makedirs(output_dir, exist_ok=True)
    filters = [w.strip().lower() for w in (weights or []) if w.strip()]

    with tempfile.TemporaryDirectory(prefix="dgs_fonts_") as workdir:
        archive_path = os.path.join(workdir, "fonts.zip")
        extract_dir = os.path.join(workdir, "extracted")

        print(f"Downloading font archive: {zip_url}")
        try:
            request = urllib.request.Request(zip_url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                with open(archive_path, "wb") as handle:
                    handle.write(response.read())
        except Exception as exc:  # noqa: BLE001 - report and return, do not raise
            print(f"Failed to download the archive: {exc}")
            return 0

        try:
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            print(f"Not a valid zip archive: {exc}")
            return 0

        copied = 0
        for root, _dirs, files in os.walk(extract_dir):
            for name in sorted(files):
                if not name.lower().endswith(FONT_EXTENSIONS):
                    continue
                if filters and not any(f in name.lower() for f in filters):
                    continue
                shutil.copy2(os.path.join(root, name), os.path.join(output_dir, name))
                print(f"Extracted: {name}")
                copied += 1

    if not copied:
        print("No font matched the filter. Run again with a shorter filter, or none at all.")
    else:
        print(f"Finished. {copied} font file(s) in {output_dir}.")
    return copied


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download_fonts.py",
        description="Stage 4: download a font archive and extract selected weights.",
        epilog="Example: download_fonts.py https://example.com/Inter.zip fonts Regular,Bold",
    )
    parser.add_argument("zip_url", nargs="?", help="URL of a zip archive containing fonts")
    parser.add_argument("output_dir", nargs="?", default="fonts", help="where to copy the fonts")
    parser.add_argument("weights", nargs="?", help="comma-separated name filters, for example Regular,Bold")
    parser.add_argument("--config", help="JSON config file; overrides the positional arguments")
    parser.add_argument("--timeout", type=float, default=120.0, help="download timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    zip_url = args.zip_url
    output_dir = args.output_dir
    weights = args.weights.split(",") if args.weights else []

    if args.config:
        with open(args.config, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        fonts_cfg = config.get("fonts") or {}
        zip_url = fonts_cfg.get("url") or zip_url
        output_dir = fonts_cfg.get("output") or output_dir
        weights = fonts_cfg.get("weights") or weights

    if not zip_url:
        print("No font archive configured. This stage is optional: skip it, or set fonts.url.")
        return 0

    download_and_extract_fonts(zip_url, output_dir, weights, timeout=args.timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
