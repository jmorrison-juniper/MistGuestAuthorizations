"""Check landing-page structure, local links, and captured screenshot files."""

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_landing_readme_has_only_the_six_required_sections(self):
        readme = (ROOT / "README.md").read_text()
        headings = re.findall(r"^#{2,6} (.+)$", readme, re.MULTILINE)
        self.assertEqual(headings, ["What", "How", "Where", "When", "Why", "Who"])
        images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
        self.assertGreaterEqual(len(set(images)), 4)

    def test_documentation_local_links_and_heading_anchors_exist(self):
        documents = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
        for document in documents:
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", document.read_text()):
                if "://" in target or target.startswith("mailto:"):
                    continue
                path, _, anchor = target.partition("#")
                destination = document.parent / path if path else document
                with self.subTest(document=document.relative_to(ROOT), target=target):
                    self.assertTrue(destination.is_file(), f"Missing link: {target}")
                    if anchor:
                        headings = re.findall(
                            r"^#+ (.+)$", destination.read_text(), re.MULTILINE
                        )
                        slugs = [
                            re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
                            for heading in headings
                        ]
                        self.assertIn(anchor, slugs)

    def test_screenshots_are_full_size_png_captures(self):
        screenshots = sorted((ROOT / "docs" / "screenshots").glob("*.png"))
        self.assertEqual(len(screenshots), 7)
        for screenshot in screenshots:
            with self.subTest(screenshot=screenshot.name):
                header = screenshot.read_bytes()[:24]
                self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
                width, height = struct.unpack(">II", header[16:24])
                self.assertEqual(width, 1440)
                self.assertGreaterEqual(height, 1080)


if __name__ == "__main__":
    unittest.main()
