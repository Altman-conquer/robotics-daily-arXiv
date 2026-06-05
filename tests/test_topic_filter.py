import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import topic_filter  # noqa: E402


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeChain:
    def __init__(self, content):
        self.content = content

    def invoke(self, payload):
        return FakeResponse(self.content)


class TopicFilterParsingTest(unittest.TestCase):
    def test_parses_plain_classifier_json(self):
        result = topic_filter.parse_classifier_response(
            '{"relevant": false, "confidence": 0.95, "reason": "generic image generation", "topics": ["CV"]}'
        )

        self.assertFalse(result["relevant"])
        self.assertEqual(result["confidence"], 0.95)
        self.assertEqual(result["reason"], "generic image generation")
        self.assertEqual(result["topics"], ["CV"])

    def test_parses_fenced_classifier_json(self):
        result = topic_filter.parse_classifier_response(
            """```json
            {"relevant": true, "reason": "robot manipulation"}
            ```"""
        )

        self.assertTrue(result["relevant"])
        self.assertEqual(result["reason"], "robot manipulation")

    def test_invalid_classifier_json_fails_open(self):
        result = topic_filter.parse_classifier_response("not json")

        self.assertTrue(result["relevant"])
        self.assertIn("failed open", result["reason"])

    @patch.dict("os.environ", {"TOPIC_FILTER_KEEP_UNCERTAIN": "true", "TOPIC_FILTER_MIN_CONFIDENCE": "0.65"})
    def test_classifier_keeps_uncertain_rejection(self):
        result = topic_filter.classify_item(
            FakeChain('{"relevant": false, "confidence": 0.4, "reason": "borderline", "topics": []}'),
            {"id": "x", "title": "Maybe embodied", "summary": "borderline paper"},
            "embodied AI",
        )

        self.assertTrue(result["relevant"])
        self.assertIn("uncertain_keep", result["reason"])

    @patch.dict("os.environ", {"TOPIC_FILTER_KEEP_UNCERTAIN": "true", "TOPIC_FILTER_MIN_CONFIDENCE": "0.65"})
    def test_classifier_rejects_confident_irrelevant_paper(self):
        result = topic_filter.classify_item(
            FakeChain('{"relevant": false, "confidence": 0.95, "reason": "generic CV", "topics": ["CV"]}'),
            {"id": "x", "title": "Image compression", "summary": "generic computer vision paper"},
            "embodied AI",
        )

        self.assertFalse(result["relevant"])
        self.assertEqual(result["reason"], "generic CV")


if __name__ == "__main__":
    unittest.main()
