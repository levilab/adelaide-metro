import unittest
from datetime import date

from google.transit import gtfs_realtime_pb2

from streaming.consumer import parse_entity_to_rows


class TestParseVehiclePosition(unittest.TestCase):

    def test_parses_vehicle_position_into_one_row(self):
        # Arrange
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "vehicle-entity-1"

        vehicle_position = entity.vehicle

        vehicle_position.trip.trip_id = "trip-400"
        vehicle_position.trip.route_id = "route-20"
        vehicle_position.trip.direction_id = 0
        vehicle_position.trip.start_date = "20260929"
        vehicle_position.trip.schedule_relationship = (
            gtfs_realtime_pb2.TripDescriptor.SCHEDULED
        )

        vehicle_position.vehicle.id = "vehicle-50"
        vehicle_position.vehicle.label = "Bus 50"

        vehicle_position.position.latitude = -34.9285
        vehicle_position.position.longitude = 138.6007
        vehicle_position.position.bearing = 90.0
        vehicle_position.position.speed = 12.5

        vehicle_position.timestamp = 1780100300

        vehicle_position.occupancy_status = (gtfs_realtime_pb2.VehiclePosition.STANDING_ROOM_ONLY)

        headers = {
            "fetched_at": "2026-09-29T10:30:00+09:30",
            "feed_timestamp": "1780100000",
        }

        # Act
        rows = parse_entity_to_rows(
            "gtfs.vehicle_positions",
            entity,
            headers,
        )

        # Assert
        self.assertEqual(len(rows), 1)

        row = rows[0]

        self.assertEqual(row["entity_id"], "vehicle-entity-1")
        self.assertEqual(row["trip_id"], "trip-400")
        self.assertEqual(row["route_id"], "route-20")
        self.assertEqual(row["direction_id"], 0)
        self.assertEqual(row["start_date"], "2026-09-29")
        self.assertEqual(
            row["schedule_relationship"],
            "SCHEDULED",
        )

        self.assertEqual(row["vehicle_id"], "vehicle-50")
        self.assertEqual(row["vehicle_label"], "Bus 50")

        self.assertAlmostEqual(
            row["latitude"],
            -34.9285,
            delta=0.0001,
        )
        self.assertAlmostEqual(
            row["longitude"],
            138.6007,
            delta=0.0001,
        )
        self.assertAlmostEqual(row["bearing"], 90.0)
        self.assertAlmostEqual(row["speed"], 12.5)

        self.assertEqual(
            int(row["vehicle_timestamp"].timestamp()),
            1780100300,
        )
        self.assertEqual(
            row["fetched_date"],
            date(2026, 9, 29),
        )

        self.assertEqual(
            row["schedule_relationship"],
            "SCHEDULED",
            )

        self.assertEqual(
            row["occupancy_status"],
            "STANDING_ROOM_ONLY",
        )


if __name__ == "__main__":
    unittest.main()
