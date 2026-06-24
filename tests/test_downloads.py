from __future__ import annotations

import gzip
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepseekcell_ft.downloads import download_panglaodb_markers


class DownloadsTests(unittest.TestCase):
    def test_download_panglaodb_markers_decompresses_table(self) -> None:
        payload = gzip.compress(b"species\tofficial gene symbol\tcell type\torgan\nHs\tIL7R\tT cells\tBlood\n")

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                if getattr(self, "_used", False):
                    return b""
                self._used = True
                return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "panglaodb.tsv"
            with patch("urllib.request.urlopen", return_value=FakeResponse()):
                result = download_panglaodb_markers(output_path, url="https://example.test/file.gz")

            text = result.read_text(encoding="utf-8")

        self.assertIn("official gene symbol", text)
        self.assertIn("IL7R", text)
