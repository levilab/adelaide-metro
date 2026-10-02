import unittest
from unittest.mock import patch

from google.api_core.exceptions import (
    Forbidden,
    InternalServerError,
)

from streaming.consumer import run_topic_worker


class TestWorkerRecovery(unittest.TestCase):

    def test_restarts_after_temporary_bigquery_error_easy_to_read(self):
        config = {"table_name": "test_table"}

        # Create two separate mocks
        mock_worker = patch("streaming.consumer.process_topic_consumer")
        mock_sleep = patch("streaming.consumer.time.sleep")

        # start initialzing mocks
        worker_func = mock_worker.start()
        sleep_func = mock_sleep.start()

        # config the returned error after the first failure, then stop at the second failure
        worker_func.side_effect = [
            InternalServerError("backend failure"),
            KeyboardInterrupt(),
        ]

        # test the function and capture KeyboardInterrupt
        try:
            run_topic_worker("gtfs.feed_status", config)
        except KeyboardInterrupt:
            pass

        # Verify the result
        self.assertEqual(worker_func.call_count, 2)
        sleep_func.assert_called_once_with(5)

        # Stop mocks
        mock_worker.stop()
        mock_sleep.stop()

