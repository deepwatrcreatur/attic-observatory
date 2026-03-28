import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app


class ParseBoundedIntArgTests(unittest.TestCase):
    def test_returns_default_when_missing(self) -> None:
        self.assertEqual(
            app.parse_bounded_int_arg({}, "limit", default=100, minimum=1, maximum=500),
            100,
        )

    def test_clamps_to_bounds(self) -> None:
        self.assertEqual(
            app.parse_bounded_int_arg({"limit": ["0"]}, "limit", default=100, minimum=1, maximum=500),
            1,
        )
        self.assertEqual(
            app.parse_bounded_int_arg({"limit": ["999"]}, "limit", default=100, minimum=1, maximum=500),
            500,
        )

    def test_rejects_non_integer_values(self) -> None:
        with self.assertRaisesRegex(app.QueryValidationError, "must be an integer"):
            app.parse_bounded_int_arg({"limit": ["abc"]}, "limit", default=100, minimum=1, maximum=500)

    def test_uses_default_for_empty_value_list(self) -> None:
        self.assertEqual(
            app.parse_bounded_int_arg({"limit": []}, "limit", default=100, minimum=1, maximum=500),
            100,
        )


class _FakeSocket:
    def __init__(self, request_text: str) -> None:
        self._rfile = io.BytesIO(request_text.encode("utf-8"))
        self._wfile = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs):
        if "r" in mode:
            return self._rfile
        if "w" in mode:
            return self._wfile
        raise ValueError(f"Unsupported mode: {mode}")

    def sendall(self, data: bytes) -> None:
        self._wfile.write(data)

    def close(self) -> None:
        pass


class _FakeServer:
    server_name = "testserver"
    server_port = 8088


class AppHandlerTests(unittest.TestCase):
    def test_uploads_returns_400_for_invalid_limit(self) -> None:
        request = _FakeSocket("GET /uploads?limit=abc HTTP/1.1\r\nHost: localhost\r\n\r\n")
        app.AppHandler(request, ("127.0.0.1", 12345), _FakeServer())
        response = request._wfile.getvalue().decode("utf-8", errors="replace")
        self.assertIn("400 Bad Request", response)
        self.assertIn("must be an integer", response)


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
