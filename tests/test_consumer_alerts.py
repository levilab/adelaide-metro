import unittest

from google.transit import gtfs_realtime_pb2

from streaming.consumer import parse_entity_to_rows


class TestParseServiceAlert(unittest.TestCase):

    def test_creates_one_row_per_informed_route(self):
        # Arrange
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "alert-1"

        alert = entity.alert

        active_period = alert.active_period.add()
        active_period.start = 1740688200

        first_route = alert.informed_entity.add()
        first_route.route_id = "98C"

        second_route = alert.informed_entity.add()
        second_route.route_id = "99C"

        alert.cause = gtfs_realtime_pb2.Alert.UNKNOWN_CAUSE
        alert.effect = gtfs_realtime_pb2.Alert.UNKNOWN_EFFECT

        header_translation = alert.header_text.translation.add()
        header_translation.text = "Stop change"
        header_translation.language = "en"

        description_translation = (
            alert.description_text.translation.add()
        )
        description_translation.text = (
            "<div><p>Stop temporarily "
            "<strong>relocated</strong>&nbsp;</p></div>")
        description_translation.language = "en"

        url_translation = alert.url.translation.add()
        url_translation.text = "https://example.com/alert-1"
        url_translation.language = "en"

        headers = {
            "fetched_at": (
                "2026-09-29T10:30:00+09:30"
            ),
            "feed_timestamp": "1780100000",
        }

        # Act
        rows = parse_entity_to_rows(
            "gtfs.service_alerts",
            entity,
            headers,
        )

        # Assert
        self.assertEqual(len(rows), 2)

        self.assertEqual(
            [row["route_id"] for row in rows],
            ["98C", "99C"],
        )

        for row in rows:
            self.assertEqual(row["entity_id"], "alert-1")
            self.assertEqual(row["header_text"], "Stop change")
            self.assertEqual(
                row["description_text"],
                "<div><p>Stop temporarily "
                "<strong>relocated</strong>&nbsp;</p></div>",
            )
            self.assertEqual(
                row["url"],
                "https://example.com/alert-1",
            )

            self.assertEqual(
                row["cause"],
                "UNKNOWN_CAUSE",
            )

            self.assertEqual(
                row["effect"],
                "UNKNOWN_EFFECT",
            )
