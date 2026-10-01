import unittest

from streaming.consumer import (
    gtfs_date_to_string,
    parse_kafka_headers,
    should_flush_batch,
)

class TestGtfsDateToString(unittest.TestCase):

    def test_converts_gtfs_to_isoformat(self):
        # Arrange
        gtfs_date = "20260929"

        # Act
        result = gtfs_date_to_string(gtfs_date)

        # Assert
        self.assertEqual(result, "2026-09-29")

    def test_return_none_for_empty_input(self):
         # Arrange
        gtfs_date = ""

        # Act
        result = gtfs_date_to_string(gtfs_date)

        # Assert
        self.assertIsNone(result)

class TestParseKafkaHeaders(unittest.TestCase):

    def test_decodes_kafka_header_bytes(self):
        # Arrange
        headers = [
            ("fetched_at", b"2026-09-29T10:30:00+09:30"),
            ("feed_timestamp", b"1780000000")
        ]
        # Act
        result = parse_kafka_headers(headers)

        # Assert
        self.assertEqual(
            result,
            {
                    "fetched_at": "2026-09-29T10:30:00+09:30",
                    "feed_timestamp": "1780000000"
                }
        )

    def test_preserves_missing_header_value_as_none(self):
        headers = [
            ("feed_timestamp", None),
        ]

        result = parse_kafka_headers(headers)

        self.assertEqual(
            result,
            {
                "feed_timestamp": None,
            },
        )

    def test_returns_empty_dict_when_headers_are_empty(self):
        result = parse_kafka_headers([])

        self.assertEqual(result, {}) 

class TestShouldFlushBatch(unittest.TestCase):

    def test_empty_buffer_does_not_flush(self):
        self.assertFalse(
            should_flush_batch(0, elapsed_seconds=60)
        )

    def test_row_limit_triggers_flush(self):
        self.assertTrue(
            should_flush_batch(5000, elapsed_seconds=1)
        )

    def test_time_limit_triggers_flush(self):
        self.assertTrue(
            should_flush_batch(10, elapsed_seconds=30)
        )

    def test_below_both_limits_keeps_buffering(self):
        self.assertFalse(
            should_flush_batch(4999, elapsed_seconds=29.9)
        ) 

if __name__=="__main__":
    unittest.main()
