from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app


class ExtractStorePathHashTests(unittest.TestCase):
    def test_extracts_hash_from_nix_store_path(self) -> None:
        self.assertEqual(
            app.extract_store_path_hash("/nix/store/0123456789abcdfghijklmnpqrsvwxyz-example-package"),
            "0123456789abcdfghijklmnpqrsvwxyz",
        )

    def test_rejects_non_store_paths(self) -> None:
        self.assertIsNone(app.extract_store_path_hash("relative/path"))
        self.assertIsNone(app.extract_store_path_hash("/nix/store/not-a-store-path"))


class RenderReferenceItemTests(unittest.TestCase):
    def test_links_store_path_references(self) -> None:
        item = app.render_reference_item("/nix/store/0123456789abcdfghijklmnpqrsvwxyz-example-package", "x-dark")
        self.assertIn('/object/0123456789abcdfghijklmnpqrsvwxyz?theme=x-dark', item)

    def test_keeps_non_store_path_references_plain(self) -> None:
        item = app.render_reference_item("plain-reference", "x-dark")
        self.assertEqual(item, "<li><code>plain-reference</code></li>")


if __name__ == "__main__":
    unittest.main()
