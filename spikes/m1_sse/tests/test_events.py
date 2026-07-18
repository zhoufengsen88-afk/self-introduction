import unittest

from spikes.m1_sse.events import encode_sse, parse_sse_frame


class SseEventTests(unittest.TestCase):
    def test_encode_and_parse_sse_event(self):
        encoded = encode_sse(
            "delta",
            {"content": "你好", "index": 1},
            event_id="session:1",
        )
        self.assertTrue(encoded.endswith("\n\n"))
        parsed = parse_sse_frame(encoded.strip())
        self.assertEqual(parsed.event, "delta")
        self.assertEqual(parsed.event_id, "session:1")
        self.assertEqual(parsed.data["content"], "你好")


if __name__ == "__main__":
    unittest.main()
