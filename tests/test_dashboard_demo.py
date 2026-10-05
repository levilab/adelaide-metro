import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest


class TestDashboardRefresh(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        st.cache_resource.clear()
        self.client = MagicMock()
        self.client.query.side_effect = self.query
        self.frames = {
            "mart_dashboard_network_kpi": pd.DataFrame([{
                "total_stops": 1, "total_departures": 10, "total_routes": 2,
                "top_stop": "Test Stop", "busiest_route": "A",
                "busiest_route_trips": 5, "peak_hour": 8,
            }]),
            "mart_dashboard_stop_map": pd.DataFrame([{
                "stop_id": "1", "stop_name": "Test Stop", "stop_lat": -34.9,
                "stop_lon": 138.6, "total_departures": 10, "route_type": 3,
                "lga_name": "Adelaide",
            }]),
            "mart_dashboard_lga_service": pd.DataFrame([{
                "lga_name": "Adelaide", "stop_count": 1,
                "route_count": 2, "scheduled_stop_visits": 10,
            }]),
            "mart_dashboard_route_trip_counts": pd.DataFrame([{
                "route_short_name": "A", "route_long_name": "Test Route",
                "route_type": 3, "total_trips": 5,
            }]),
            "mart_dashboard_coverage_hubs": pd.DataFrame(),
            "mart_dashboard_route_lengths": pd.DataFrame([{
                "route_id": "A", "route_short_name": "A", "route_long_name": "Test Route",
                "route_type": 3, "avg_length_km": 10.0,
                "min_length_km": 8.0, "max_length_km": 12.0, "shape_count": 2,
            }]),
            "mart_dashboard_cbd_corridor_speed": pd.DataFrame([{
                "corridor_name": "King William St",
                "time_bucket": "AM Peak (7-9h)",
                "unique_trips": 5, "corridor_avg_speed_kmh": 15.0,
            }]),
            "mart_dashboard_delay_propagation": pd.DataFrame([
                {
                    "route_short_name": route, "stop_sequence": sequence,
                    "stop_name": f"Stop {sequence}", "total_trips_analyzed": 2,
                    "avg_delay_mins": float(sequence), "delay_added_mins": 1.0,
                    "propagation_factor": float(sequence),
                    "data_as_of": pd.Timestamp("2026-10-03T00:00:00Z"),
                }
                for route in ("A", "B") for sequence in (1, 2)
            ]),
        }

    def tearDown(self):
        st.cache_data.clear()
        st.cache_resource.clear()

    def query(self, sql, **kwargs):
        for name, frame in self.frames.items():
            if f".marts.{name}`" in sql:
                job = MagicMock()
                job.to_dataframe.side_effect = lambda **kwargs: frame.copy(deep=True)
                return job
        raise AssertionError(f"Unexpected dashboard query: {sql}")

    def query_count(self, mart):
        return sum(mart in call.args[0] for call in self.client.query.call_args_list)

    def test_render_route_selection_and_refresh_preserve_static_cache(self):
        app_path = Path(__file__).resolve().parents[1] / "dashboard" / "App.py"
        with (
            patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "dashboard-test", "DASHBOARD_MODE": "live"}),
            patch("google.cloud.bigquery.Client", return_value=self.client),
            patch("streamlit_autorefresh.st_autorefresh") as autorefresh,
        ):
            app = AppTest.from_file(str(app_path), default_timeout=30).run()
            self.assertEqual(len(app.exception), 0, app.exception)
            self.assertEqual(len(app.tabs), 6)
            autorefresh.assert_called_once_with(
                interval=300000, key="delay_tab_autorefresh"
            )

            app.selectbox(key="delay_selected_route").select("B").run()
            self.assertEqual(len(app.exception), 0, app.exception)
            self.assertEqual(app.selectbox(key="delay_selected_route").value, "B")
            self.assertEqual(self.query_count("mart_dashboard_delay_propagation"), 1)

            self.frames["mart_dashboard_delay_propagation"]["avg_delay_mins"] = 9.0
            refresh = next(button for button in app.button if "Refresh Data" in button.label)
            refresh.click().run()
            self.assertEqual(len(app.exception), 0, app.exception)
            self.assertEqual(app.selectbox(key="delay_selected_route").value, "B")
            self.assertEqual(self.query_count("mart_dashboard_delay_propagation"), 2)
            self.assertEqual(self.query_count("mart_dashboard_network_kpi"), 1)
            self.assertTrue(
                any(metric.delta == "9.0 mins" for metric in app.metric),
                [(metric.label, metric.value, metric.delta) for metric in app.metric],
            )

    def test_demo_uses_saved_data_without_automatic_refresh(self):
        app_path = Path(__file__).resolve().parents[1] / "dashboard" / "App.py"
        with (
            patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "dashboard-test", "DASHBOARD_MODE": "demo"}),
            patch("google.cloud.bigquery.Client", return_value=self.client),
            patch("streamlit_autorefresh.st_autorefresh") as autorefresh,
        ):
            app = AppTest.from_file(str(app_path), default_timeout=30).run()
            self.assertEqual(len(app.exception), 0, app.exception)
            autorefresh.assert_not_called()
            self.assertTrue(any("Demo dataset" in info.value for info in app.info))
            self.assertTrue(any("Saved data as of: 03 Oct 2026" in caption.value for caption in app.caption))


if __name__ == "__main__":
    unittest.main()
