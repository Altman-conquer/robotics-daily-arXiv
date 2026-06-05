import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


AI_DIR = Path(__file__).resolve().parents[1] / "ai"
sys.path.insert(0, str(AI_DIR))
PREVIOUS_CWD = Path.cwd()

try:
    os.chdir(AI_DIR)
    import enhance  # noqa: E402
finally:
    os.chdir(PREVIOUS_CWD)


class EnhanceJsonParsingTest(unittest.TestCase):
    def test_parses_plain_json_response(self):
        result = enhance.parse_ai_json_response(
            """
            {
              "tldr": "short summary",
              "motivation": "why it matters",
              "method": "what was done",
              "result": "what happened",
              "conclusion": "what it means"
            }
            """,
            enhance.DEFAULT_AI_FIELDS,
        )

        self.assertEqual(result["tldr"], "short summary")
        self.assertEqual(result["method"], "what was done")

    def test_parses_fenced_json_with_trailing_text(self):
        result = enhance.parse_ai_json_response(
            """```json
            {
              "tldr": "short summary",
              "motivation": "why it matters",
              "method": "what was done",
              "result": "what happened",
              "conclusion": "what it means"
            }
            ```
            extra text""",
            enhance.DEFAULT_AI_FIELDS,
        )

        self.assertEqual(result["conclusion"], "what it means")

    def test_uses_defaults_for_invalid_json(self):
        result = enhance.parse_ai_json_response(
            "not json",
            enhance.DEFAULT_AI_FIELDS,
        )

        self.assertEqual(result, enhance.DEFAULT_AI_FIELDS)

    @patch("enhance.requests.post")
    def test_sensitive_checker_fails_open_on_request_error(self, post):
        post.side_effect = RuntimeError("network unavailable")

        self.assertFalse(enhance.is_sensitive_content("paper summary"))

    @patch("enhance.requests.post")
    def test_sensitive_checker_fails_open_on_non_200_status(self, post):
        post.return_value = Mock(status_code=503)

        self.assertFalse(enhance.is_sensitive_content("paper summary"))

    @patch("enhance.requests.post")
    def test_sensitive_checker_requires_explicit_true(self, post):
        response = Mock(status_code=200)
        response.json.return_value = {}
        post.return_value = response

        self.assertFalse(enhance.is_sensitive_content("paper summary"))

        response.json.return_value = {"sensitive": True}
        self.assertTrue(enhance.is_sensitive_content("paper summary"))


if __name__ == "__main__":
    unittest.main()
