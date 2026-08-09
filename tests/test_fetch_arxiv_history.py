import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_arxiv_history as history  # noqa: E402


class FetchArxivHistoryTests(unittest.TestCase):
    def test_build_query_uses_inclusive_submission_dates(self):
        query = history.build_query(
            ["cs.RO", "cs.CV"],
            date(2026, 7, 10),
            date(2026, 7, 14),
        )
        self.assertEqual(
            query,
            "(cat:cs.RO OR cat:cs.CV) AND "
            "submittedDate:[202607100000 TO 202607142359]",
        )

    def test_build_chunks_covers_range_without_overlap(self):
        self.assertEqual(
            history.build_chunks(date(2026, 7, 10), date(2026, 7, 21), 5),
            [
                {"start": "2026-07-10", "end": "2026-07-14"},
                {"start": "2026-07-15", "end": "2026-07-19"},
                {"start": "2026-07-20", "end": "2026-07-21"},
            ],
        )

    def test_normalize_arxiv_id_removes_version(self):
        self.assertEqual(
            history.normalize_arxiv_id("https://arxiv.org/abs/2608.06375v2"),
            "2608.06375",
        )

    def test_paper_to_item_matches_daily_pipeline_shape(self):
        paper = SimpleNamespace(
            entry_id="https://arxiv.org/abs/2608.06375v1",
            authors=[SimpleNamespace(name="First  Author"), SimpleNamespace(name="Second")],
            title="A  title\nwith whitespace",
            categories=["cs.RO", "cs.AI"],
            comment=None,
            summary="An abstract.\n More text.",
            published=datetime(2026, 8, 6, 17, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(
            history.paper_to_item(paper),
            {
                "id": "2608.06375",
                "pdf": "https://arxiv.org/pdf/2608.06375",
                "abs": "https://arxiv.org/abs/2608.06375",
                "authors": ["First Author", "Second"],
                "title": "A title with whitespace",
                "categories": ["cs.RO", "cs.AI"],
                "comment": "",
                "summary": "An abstract. More text.",
            },
        )


if __name__ == "__main__":
    unittest.main()
