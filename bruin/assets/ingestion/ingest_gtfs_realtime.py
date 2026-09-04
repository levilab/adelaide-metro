"""@bruin
name: streaming.ingest_gtfs_realtime
type: python
connection: gcp
materialization:
  type: table
requirements:
  - python-dotenv
  - requests
  - pandas
  - pyarrow
  - google-cloud-bigquery
  - google-cloud-storage
  - gtfs-realtime-bindings
@bruin"""

import os
import re
import html
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google.cloud import bigquery, storage
from google.transit import gtfs_realtime_pb2

load_dotenv()

# Múi giờ Adelaide
ADELAIDE_TZ = ZoneInfo("Australia/Adelaide")

GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "adelaide-metro-505702")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "adelaide-metro-505702-raw")
GCS_PREFIX = "gtfs_realtime/adelaide-metro"
BQ_DATASET = "streaming"

HEADERS = {"accept": "application/x-google-protobuf"}

FEEDS = {
    "trip_updates": "https://gtfs.adelaidemetro.com.au/v1/realtime/trip_updates",
    "service_alerts": "https://gtfs.adelaidemetro.com.au/v1/realtime/service_alerts",
    "vehicle_positions": "https://gtfs.adelaidemetro.com.au/v1/realtime/vehicle_positions",
}


def epoch_to_adelaide_datetime(epoch_seconds):
    """Đổi epoch timestamp về Datetime thuộc múi giờ Adelaide."""
    if not epoch_seconds:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=ADELAIDE_TZ)


def gtfs_date_to_string(date_value):
    if not date_value:
        return None
    return f"{date_value[:4]}-{date_value[4:6]}-{date_value[6:8]}"


def first_translation(translated_string):
    if not translated_string or not translated_string.translation:
        return None
    return translated_string.translation[0].text or None


def clean_html(value):
    if not value:
        return None
    text = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def download_and_parse(feed_name, url, bucket):
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()

    # Lấy thời gian hiện tại theo múi giờ Adelaide
    now_adelaide = datetime.now(ADELAIDE_TZ)
    
    ingested_at = now_adelaide
    ingested_date = now_adelaide.date()  # Dùng làm Partition Key trong BigQuery

    # Tên file GCS lưu vết theo giờ Adelaide
    gcs_path = f"{GCS_PREFIX}/{feed_name}/{now_adelaide:%Y%m%dT%H%M%S%z}.pb"
    bucket.blob(gcs_path).upload_from_string(
        response.content,
        content_type="application/x-google-protobuf",
    )
    print(f"Uploaded {feed_name} raw protobuf -> gs://{GCS_BUCKET}/{gcs_path}")

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed, ingested_at, ingested_date, f"gs://{GCS_BUCKET}/{gcs_path}"


def base_row(feed, ingested_at, ingested_date, source_gcs_uri):
    return {
        "ingested_date": ingested_date,  # Partition column (YYYY-MM-DD theo giờ Adelaide)
        "ingested_at": ingested_at,
        "feed_timestamp": epoch_to_adelaide_datetime(feed.header.timestamp),
        "source_gcs_uri": source_gcs_uri,
    }


def parse_trip_updates(feed, ingested_at, ingested_date, source_gcs_uri):
    rows = []
    for entity in feed.entity:
        if entity.HasField("trip_update"):
            trip_update = entity.trip_update
            trip = trip_update.trip
            vehicle = trip_update.vehicle

            for stop_update in trip_update.stop_time_update:
                rows.append(
                    {
                        **base_row(feed, ingested_at, ingested_date, source_gcs_uri),
                        "entity_id": entity.id,
                        "trip_id": trip.trip_id,
                        "route_id": trip.route_id,
                        "direction_id": trip.direction_id,
                        "start_date": gtfs_date_to_string(trip.start_date),
                        "vehicle_id": vehicle.id if vehicle.id else None,
                        "vehicle_label": vehicle.label if vehicle.label else None,
                        "trip_update_timestamp": epoch_to_adelaide_datetime(trip_update.timestamp),
                        "stop_id": stop_update.stop_id,
                        "stop_sequence": stop_update.stop_sequence,
                        "arrival_time": epoch_to_adelaide_datetime(stop_update.arrival.time)
                        if stop_update.HasField("arrival")
                        else None,
                        "arrival_delay_seconds": stop_update.arrival.delay
                        if stop_update.HasField("arrival")
                        else None,
                        "departure_time": epoch_to_adelaide_datetime(stop_update.departure.time)
                        if stop_update.HasField("departure")
                        else None,
                        "departure_delay_seconds": stop_update.departure.delay
                        if stop_update.HasField("departure")
                        else None,
                    }
                )
    return pd.DataFrame(rows)


def parse_service_alerts(feed, ingested_at, ingested_date, source_gcs_uri):
    alert_rows = []
    informed_entity_rows = []

    for entity in feed.entity:
        if entity.HasField("alert"):
            alert = entity.alert
            active_starts = [period.start for period in alert.active_period if period.start]
            active_ends = [period.end for period in alert.active_period if period.end]

            alert_rows.append(
                {
                    **base_row(feed, ingested_at, ingested_date, source_gcs_uri),
                    "entity_id": entity.id,
                    "cause": alert.cause,
                    "effect": alert.effect,
                    "header_text": first_translation(alert.header_text),
                    "description_text": clean_html(first_translation(alert.description_text)),
                    "active_start": epoch_to_adelaide_datetime(min(active_starts)) if active_starts else None,
                    "active_end": epoch_to_adelaide_datetime(max(active_ends)) if active_ends else None,
                }
            )

            for item in alert.informed_entity:
                trip_id = item.trip.trip_id if item.HasField("trip") else None
                informed_entity_rows.append(
                    {
                        **base_row(feed, ingested_at, ingested_date, source_gcs_uri),
                        "alert_entity_id": entity.id,
                        "route_id": item.route_id or None,
                    }
                )

    return pd.DataFrame(alert_rows), pd.DataFrame(informed_entity_rows)


def parse_vehicle_positions(feed, ingested_at, ingested_date, source_gcs_uri):
    rows = []
    for entity in feed.entity:
        if entity.HasField("vehicle"):
            vehicle_position = entity.vehicle
            trip = vehicle_position.trip
            position = vehicle_position.position
            vehicle = vehicle_position.vehicle

            rows.append(
                {
                    **base_row(feed, ingested_at, ingested_date, source_gcs_uri),
                    "entity_id": entity.id,
                    "trip_id": trip.trip_id,
                    "route_id": trip.route_id,
                    "direction_id": trip.direction_id,
                    "start_date": gtfs_date_to_string(trip.start_date),
                    "vehicle_id": vehicle.id,
                    "vehicle_label": vehicle.label,
                    "latitude": position.latitude,
                    "longitude": position.longitude,
                    "bearing": position.bearing,
                    "speed": position.speed,
                    "current_stop_sequence": vehicle_position.current_stop_sequence,
                    "stop_id": vehicle_position.stop_id,
                    "vehicle_timestamp": epoch_to_adelaide_datetime(vehicle_position.timestamp),
                }
            )
    return pd.DataFrame(rows)


def load_to_bigquery(bq_client, df, table_name):
    if df.empty:
        print(f"No rows for {table_name}, skipping BigQuery load")
        return

    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{table_name}"

    job_config = bigquery.LoadJobConfig(
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="ingested_date",
        ),
    )
    load_job = bq_client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    load_job.result()
    print(f"Loaded {len(df)} rows -> {table_ref} [APPEND & PARTITIONED BY ADELAIDE DATE]")


def materialize():
    storage_client = storage.Client(project=GCP_PROJECT)
    bq_client = bigquery.Client(project=GCP_PROJECT)
    bucket = storage_client.bucket(GCS_BUCKET)

    # 1. Ingest Trip Updates
    trip_feed, ingested_at, ingested_date, source_gcs_uri = download_and_parse(
        "trip_updates", FEEDS["trip_updates"], bucket
    )
    trip_updates = parse_trip_updates(trip_feed, ingested_at, ingested_date, source_gcs_uri)
    load_to_bigquery(bq_client, trip_updates, "gtfs_realtime_trip_updates")

    # 2. Ingest Service Alerts
    alert_feed, ingested_at, ingested_date, source_gcs_uri = download_and_parse(
        "service_alerts", FEEDS["service_alerts"], bucket
    )
    service_alerts, alert_entities = parse_service_alerts(alert_feed, ingested_at, ingested_date, source_gcs_uri)
    load_to_bigquery(bq_client, service_alerts, "gtfs_realtime_service_alerts")
    load_to_bigquery(bq_client, alert_entities, "gtfs_realtime_service_alert_informed_entities")

    # 3. Ingest Vehicle Positions
    vehicle_feed, ingested_at, ingested_date, source_gcs_uri = download_and_parse(
        "vehicle_positions", FEEDS["vehicle_positions"], bucket
    )
    vehicle_positions = parse_vehicle_positions(vehicle_feed, ingested_at, ingested_date, source_gcs_uri)
    load_to_bigquery(bq_client, vehicle_positions, "gtfs_realtime_vehicle_positions")

    print("Realtime ingestion complete.")


if __name__ == "__main__":
    materialize()