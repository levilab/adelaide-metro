import json
import unittest
from unittest.mock import MagicMock, patch

from google.transit import gtfs_realtime_pb2

from streaming.producer import publish_event, publish_feed_status


class TestPublishEvent(unittest.TestCase):

    def test_publishes_new_and_legacy_fetch_headers(self):
        producer = MagicMock()
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "entity-1"
        entity.trip_update.trip.trip_id = "trip-100"

        publish_event(
            producer=producer,
            topic="gtfs.trip_updates",
            entity=entity,
            feed_timestamp=1_790_000_000,
            fetched_at="2026-09-30T02:00:00+09:30",
        )

        headers = dict(
            producer.produce.call_args.kwargs["headers"]
        )
        self.assertEqual(producer.produce.call_args.kwargs["key"], b"trip_trip-100")

        self.assertEqual(
            headers["fetched_at"],
            b"2026-09-30T02:00:00+09:30",
        )
        self.assertEqual(
            headers["fetch_time_adelaide"],
            b"2026-09-30T02:00:00+09:30",
        )
        self.assertEqual(
            headers["feed_timestamp"],
            b"1790000000",
        )


class TestPublishFeedStatus(unittest.TestCase):

    @patch(
        "streaming.producer.FEED_STATUS_TOPIC",
        "gtfs.feed_status",
    )
    def test_publish_success_with_zero_entities(self):
        producer = MagicMock()

        publish_feed_status(
            producer=producer,
            feed_name="trip_updates",
            polled_at="2026-09-30T02:00:00+09:30",
            feed_timestamp=1_790_000_000,
            entity_count=0,
            http_success=True,
        )

        producer.produce.assert_called_once()

        call_arguments = producer.produce.call_args.kwargs

        self.assertEqual(
            call_arguments["topic"],
            "gtfs.feed_status",
        )
        self.assertEqual(
            call_arguments["key"],
            b"trip_updates",
        )

        payload = json.loads(
            call_arguments["value"].decode("utf-8")
        )

        self.assertEqual(payload["feed_name"], "trip_updates")
        self.assertEqual(payload["entity_count"], 0)
        self.assertTrue(payload["http_success"])
        self.assertIsNone(payload["error_message"])
        self.assertEqual(
            payload["feed_timestamp"],
            1_790_000_000,
        )

    @patch(
        "streaming.producer.FEED_STATUS_TOPIC",
        "gtfs.feed_status",
    )
    def test_publish_failed_poll(self):
        producer = MagicMock()

        publish_feed_status(
            producer=producer,
            feed_name="trip_updates",
            polled_at="2026-09-30T02:00:00+09:30",
            feed_timestamp=None,
            entity_count=0,
            http_success=False,
            error_message="request timed out",
        )

        payload = json.loads(
            producer.produce.call_args.kwargs["value"].decode(
                "utf-8"
            )
        )

        self.assertFalse(payload["http_success"])
        self.assertIsNone(payload["feed_timestamp"])
        self.assertEqual(payload["entity_count"], 0)
        self.assertEqual(
            payload["error_message"],
            "request timed out",
        )


if __name__ == "__main__":
    unittest.main()
