import unittest

from streaming.consumer import gtfs_date_to_string

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

if __name__=="__main__":
    unittest.main()