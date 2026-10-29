#!/usr/bin/env python3
"""Offline tests for the design_skill_generator pipeline.

No network access. The fixture site is served through file:// URLs, so every stage runs exactly
as it would against a live portal.

Run from the skill directory:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import functools
import http.server
import json
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compiler  # noqa: E402
import crawler  # noqa: E402
import download_assets  # noqa: E402
import download_fonts  # noqa: E402
import generate  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serve the fixture site without printing a log line per request."""

    def log_message(self, *_args) -> None:  # noqa: D102 - silence the test output
        pass


class PipelineTestCase(unittest.TestCase):
    """Shared fixture: a copy of the fixture site with absolute asset paths."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dgs_test_"))
        self.site = self.tmp / "site"
        shutil.copytree(FIXTURES / "site", self.site)

        # Make the image block point at a real file, so the asset stage has work to do.
        preview = self.site / "img" / "preview.png"
        button = self.site / "components" / "button"
        button.write_text(button.read_text().replace("__ASSET__", str(preview)))

        self.cache = self.tmp / "cache"
        self.raw = self.tmp / "raw_data"
        self.assets = self.tmp / "assets"
        self.maps = self.tmp / "url_to_assets_map.json"
        self.refs = self.tmp / "references"

        # A real HTTP server, so the crawler runs the same code path as against a live portal.
        handler = functools.partial(QuietHandler, directory=str(self.site))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def crawl(self) -> list[str]:
        return crawler.run_crawler(
            self.base_url,
            ["components", "foundations"],
            output_dir=str(self.raw),
            cache_dir=str(self.cache),
            delay=0.0,
        )


class TestCrawler(PipelineTestCase):
    def test_resolve_path(self) -> None:
        data = {"props": {"pageProps": {"pages": [1, 2]}}}
        self.assertEqual(crawler.resolve_path(data, "props.pageProps.pages"), [1, 2])
        self.assertIsNone(crawler.resolve_path(data, "props.missing.pages"))
        self.assertIsNone(crawler.resolve_path(data, "props.pageProps.pages.0"))

    def test_extract_slugs_filters_prefixes(self) -> None:
        nav = [
            {"slug": "components", "pages": [{"slug": "components/button"}]},
            {"slug": "changelog"},
        ]
        self.assertEqual(
            crawler.extract_slugs(nav, ["components", "foundations"]),
            ["components", "components/button"],
        )

    def test_crawl_writes_one_json_per_route(self) -> None:
        slugs = self.crawl()
        self.assertIn("components/button", slugs)
        self.assertIn("foundations/color", slugs)
        self.assertNotIn("changelog", slugs)

        written = (self.raw / "components" / "button.json").read_text()
        self.assertIn("Button", written)
        # Content is unwrapped from props.pageProps.page, not stored as the whole payload.
        self.assertNotIn("__NEXT_DATA__", written)

    def test_crawl_without_next_data_reports_and_stops(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "index.html").write_text("<html><body>no next data</body></html>")
        handler = functools.partial(QuietHandler, directory=str(plain))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            slugs = crawler.run_crawler(
                f"http://127.0.0.1:{server.server_address[1]}",
                ["components"],
                output_dir=str(self.tmp / "out"),
                cache_dir=str(self.cache),
                delay=0.0,
            )
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(slugs, [])


class TestCompiler(PipelineTestCase):
    def compile_button(self) -> str:
        self.crawl()
        return compiler.compile_section(
            "components", str(self.raw), str(self.tmp / "button.md"), {}
        )

    def test_rich_text_to_markdown(self) -> None:
        markdown = self.compile_button()
        self.assertIn("## Button", markdown)
        self.assertIn("The **primary** action.", markdown)
        self.assertIn("Use a button for **one** action.", markdown)
        self.assertIn("- Keep the label short", markdown)
        self.assertIn("#### Accessibility", markdown)  # heading-2 inside a section becomes h4

    def test_table_block(self) -> None:
        markdown = self.compile_button()
        self.assertIn("| Size | Height |", markdown)
        self.assertIn("| Small | 32px |", markdown)

    def test_unknown_block_is_rendered_not_dropped(self) -> None:
        markdown = self.compile_button()
        self.assertIn("Migration note", markdown)
        self.assertIn("Renamed in 2026.", markdown)
        self.assertIn("unhandled content type: alertBanner", markdown)

    def test_image_without_asset_map_is_omitted(self) -> None:
        self.assertNotIn("![", self.compile_button())

    def test_image_with_asset_map_uses_relative_path(self) -> None:
        self.crawl()
        asset_map = {"file://ignored": "components_button_states_1.png"}
        button_json = json.loads((self.raw / "components" / "button.json").read_text())
        image_url = button_json["sections"][0]["fields"]["blocks"][0]["fields"]["url"]
        markdown = compiler.compile_section(
            "components", str(self.raw), str(self.tmp / "button.md"), {image_url: asset_map["file://ignored"]}
        )
        self.assertIn("![Button states](../assets/components_button_states_1.png)", markdown)

    def test_colour_list_skips_blank_items(self) -> None:
        self.crawl()
        markdown = compiler.compile_section(
            "foundations", str(self.raw), str(self.tmp / "foundations.md"), {}
        )
        self.assertIn("| Forest | `#0B6E4F` | `#3DDC97` | `color.brand.forest` | Primary action |", markdown)
        self.assertNotIn("useAsBlank", markdown)

    def test_missing_section_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            compiler.compile_section("nope", str(self.raw), str(self.tmp / "x.md"), {})


class TestAssets(PipelineTestCase):
    def test_downloads_and_maps_images(self) -> None:
        self.crawl()
        mapping = download_assets.run_downloader(
            str(self.raw), str(self.assets), str(self.maps), delay=0.0
        )
        self.assertEqual(len(mapping), 1)
        url, name = next(iter(mapping.items()))
        self.assertIn("file://", url)
        self.assertTrue(name.endswith(".png"))
        self.assertTrue((self.assets / name).exists())
        self.assertEqual(json.loads(self.maps.read_text()), mapping)

    def test_scan_finds_direct_urls_outside_content_types(self) -> None:
        payload = {"fields": {"hero": "https://images.ctfassets.net/a/b/photo.jpg"}}
        found = download_assets.scan_for_images(payload)
        self.assertEqual(found, [("https://images.ctfassets.net/a/b/photo.jpg", "Asset")])

    def test_extension_detection(self) -> None:
        self.assertEqual(download_assets.extension_for("https://x/y.webp?w=1"), ".webp")
        self.assertEqual(download_assets.extension_for("https://x/y"), ".png")


class TestFonts(unittest.TestCase):
    def test_weight_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "fonts.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for name in ("Inter-Regular.ttf", "Inter-Bold.ttf", "Inter-SemiBold.woff2", "OFL.txt"):
                    bundle.writestr(f"Inter/{name}", "x")

            out = Path(tmp) / "out"
            copied = download_fonts.download_and_extract_fonts(
                f"file://{archive}", str(out), ["Regular"]
            )
            self.assertEqual(copied, 1)
            self.assertEqual([p.name for p in out.iterdir()], ["Inter-Regular.ttf"])

    def test_filter_is_a_substring_match(self) -> None:
        """Documented behaviour: "Bold" also matches "SemiBold"."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "fonts.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for name in ("Inter-Bold.ttf", "Inter-SemiBold.ttf"):
                    bundle.writestr(f"Inter/{name}", "x")
            out = Path(tmp) / "out"
            copied = download_fonts.download_and_extract_fonts(
                f"file://{archive}", str(out), ["Bold"]
            )
            self.assertEqual(copied, 2)

    def test_bad_archive_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "bad.zip"
            bogus.write_text("not a zip")
            copied = download_fonts.download_and_extract_fonts(f"file://{bogus}", tmp, [])
            self.assertEqual(copied, 0)


class TestGenerate(PipelineTestCase):
    def config(self, **overrides) -> dict:
        config = {
            "name": "fixture",
            "base_url": self.base_url,
            "sections": ["components", "foundations"],
            "output": {
                "raw": str(self.raw),
                "assets": str(self.assets),
                "asset_map": str(self.maps),
                "references": str(self.refs),
            },
            "fonts": {"url": None},
            "request_delay_seconds": 0.0,
            "asset_delay_seconds": 0.0,
            "cache_dir": str(self.cache),
        }
        config.update(overrides)
        return config

    def test_full_pipeline_writes_guides_and_assets(self) -> None:
        code = generate.run(self.config(), skip=set(), force=False, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((self.refs / "components.md").exists())
        self.assertTrue((self.refs / "foundations.md").exists())
        self.assertTrue(any(self.assets.iterdir()))

        guide = (self.refs / "components.md").read_text()
        self.assertIn("![Button states](../assets/", guide)

    def test_fonts_are_skipped_without_a_url(self) -> None:
        self.assertNotIn("fonts", generate.plan(self.config(), set()))
        self.assertIn("fonts", generate.plan(self.config(fonts={"url": "file://x"}), set()))

    def test_dry_run_writes_nothing(self) -> None:
        code = generate.run(self.config(), skip=set(), force=False, dry_run=True)
        self.assertEqual(code, 0)
        self.assertFalse(self.raw.exists())

    def test_crawl_failure_stops_the_run(self) -> None:
        broken = self.config(base_url=f"file://{self.tmp}/missing")
        code = generate.run(broken, skip=set(), force=False, dry_run=False)
        self.assertEqual(code, 1)

    def test_config_requires_base_url_and_sections(self) -> None:
        path = self.tmp / "bad.json"
        path.write_text(json.dumps({"name": "incomplete"}))
        with self.assertRaises(SystemExit):
            generate.load_config(str(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
