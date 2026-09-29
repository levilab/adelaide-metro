import unittest
from datetime import date

from google.transit import gtfs_realtime_pb2

from streaming.consumer import parse_entity_to_rows

class TestParseTripUpdate(unittest.TestCase):

    def test_parses_trip_update_into_row(self):
        # Arrange
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "entity-1"

        trip_update = entity.trip_update
        trip_update.trip.trip_id = "trip-100"
        trip_update.trip.schedule_relationship = (gtfs_realtime_pb2.TripDescriptor.SCHEDULED)
        trip_update.trip.route_id = "route-10"
        trip_update.trip.direction_id = 0
        trip_update.trip.start_date = "20260929"
        trip_update.vehicle.id = "vehicle-20"
        trip_update.vehicle.label = "Bus 20"
        trip_update.timestamp = 1780100000

        stop_update = trip_update.stop_time_update.add()
        stop_update.stop_sequence = 1
        stop_update.stop_id = "stop-30"
        stop_update.arrival.time = 1780100300

        headers = {
            "fetch_time_adelaide": "2026-09-29T10:30:00+09:30",
            "feed_timestamp": "1780100000",
        }

        # Act
        rows = parse_entity_to_rows(
            "gtfs.trip_updates",
            entity,
            headers,
        )

        # Assert
        self.assertEqual(len(rows), 1)

        row = rows[0]

        self.assertEqual(row["entity_id"], "entity-1")
        self.assertEqual(row["trip_id"], "trip-100")
        self.assertEqual(row["route_id"], "route-10")
        self.assertEqual(row["direction_id"], 0)
        self.assertEqual(row["schedule_relationship"], "SCHEDULED")
        self.assertEqual(row["start_date"], "2026-09-29")
        self.assertEqual(row["vehicle_id"], "vehicle-20")
        self.assertEqual(row["vehicle_label"], "Bus 20")
        self.assertEqual(row["stop_sequence"], 1)
        self.assertEqual(row["stop_id"], "stop-30")
        self.assertEqual(row["ingested_date"], date(2026, 9, 29))
        self.assertEqual(
            int(row["arrival_time"].timestamp()),
            1780100300,
        )

    def test_creates_one_row_per_stop_update(self):
        # Arrange
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "entity-multiple-stops"

        trip_update = entity.trip_update
        trip_update.trip.trip_id = "trip-300"
        trip_update.trip.route_id = "route-10"
        trip_update.trip.start_date = "20260929"

        first_stop = trip_update.stop_time_update.add()
        first_stop.stop_sequence = 1
        first_stop.stop_id = "stop-30"

        second_stop = trip_update.stop_time_update.add()
        second_stop.stop_sequence = 2
        second_stop.stop_id = "stop-40"

        headers = {
            "fetch_time_adelaide": "2026-09-29T10:30:00+09:30",
            "feed_timestamp": "1780100000",
        }

        # Act
        rows = parse_entity_to_rows(
            "gtfs.trip_updates",
            entity,
            headers,
        )

        # Assert
        self.assertEqual(len(rows), 2)

        self.assertEqual(
            [
                (row["stop_sequence"], row["stop_id"])
                for row in rows
            ],
            [
                (1, "stop-30"),
                (2, "stop-40"),
            ],
        )
        self.assertIsNone(rows[0]["schedule_relationship"])

if __name__=="__main__":
    unittest.main()