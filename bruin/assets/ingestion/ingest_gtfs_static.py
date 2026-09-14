"""@bruin
name: raw.ingest_gtfs_static
type: python
connection: gcp
materialization:
  type: table
requirements:
  - python-dotenv
  - requests
  - google-cloud-bigquery
  - google-cloud-storage
@bruin"""

import io
import os
import zipfile
import hashlib
from dotenv import load_dotenv
import requests
from google.cloud import bigquery, storage
load_dotenv()

GTFS_URL = "https://gtfs.adelaidemetro.com.au/v1/static/latest/google_transit.zip"
GCS_BUCKET  = os.environ.get("GCS_BUCKET", "adelaide-metro-505702-raw")
GCS_PREFIX  = "gtfs_static/adelaide-metro"
GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "adelaide-metro-505702")
BQ_DATASET  = "raw"

# Maps filename -> BigQuery table name
GTFS_FILES = {
    "routes.txt": "gtfs_routes",
    "stops.txt": "gtfs_stops",
    "trips.txt": "gtfs_trips",
    "stop_times.txt": "gtfs_stop_times",
    "calendar.txt": "gtfs_calendar",
    "shapes.txt": "gtfs_shapes",
}

GTFS_SCHEMAS = {
    "routes.txt": [
        bigquery.SchemaField("route_id", "STRING"),
        bigquery.SchemaField("agency_id", "STRING"),
        bigquery.SchemaField("route_short_name", "STRING"),
        bigquery.SchemaField("route_long_name", "STRING"),
        bigquery.SchemaField("route_desc", "STRING"),
        bigquery.SchemaField("route_type", "STRING"),
        bigquery.SchemaField("route_url", "STRING"),
        bigquery.SchemaField("route_color", "STRING"),
        bigquery.SchemaField("route_text_color", "STRING"),
        bigquery.SchemaField("RouteGroup", "STRING"),
    ],
    "stops.txt": [
        bigquery.SchemaField("stop_id", "STRING"),
        bigquery.SchemaField("stop_code", "STRING"),
        bigquery.SchemaField("stop_name", "STRING"),
        bigquery.SchemaField("stop_desc", "STRING"),
        bigquery.SchemaField("stop_lat", "STRING"),
        bigquery.SchemaField("stop_lon", "STRING"),
        bigquery.SchemaField("zone_id", "STRING"),
        bigquery.SchemaField("stop_url", "STRING"),
        bigquery.SchemaField("location_type", "STRING"),
        bigquery.SchemaField("parent_station", "STRING"),
        bigquery.SchemaField("stop_timezone", "STRING"),
        bigquery.SchemaField("wheelchair_boarding", "STRING"),
    ],
    "trips.txt": [
        bigquery.SchemaField("route_id", "STRING"),
        bigquery.SchemaField("service_id", "STRING"),
        bigquery.SchemaField("trip_id", "STRING"),
        bigquery.SchemaField("trip_headsign", "STRING"),
        bigquery.SchemaField("trip_short_name", "STRING"),
        bigquery.SchemaField("direction_id", "STRING"),
        bigquery.SchemaField("block_id", "STRING"),
        bigquery.SchemaField("shape_id", "STRING"),
        bigquery.SchemaField("wheelchair_accessible", "STRING"),
    ],
    "stop_times.txt": [
        bigquery.SchemaField("trip_id", "STRING"),
        bigquery.SchemaField("arrival_time", "STRING"),
        bigquery.SchemaField("departure_time", "STRING"),
        bigquery.SchemaField("stop_id", "STRING"),
        bigquery.SchemaField("stop_sequence", "STRING"),
        bigquery.SchemaField("stop_headsign", "STRING"),
        bigquery.SchemaField("pickup_type", "STRING"),
        bigquery.SchemaField("drop_off_type", "STRING"),
        bigquery.SchemaField("shape_dist_traveled", "STRING"),
        bigquery.SchemaField("timepoint", "STRING"),
        bigquery.SchemaField("pickup_booking_rule_id", "STRING"),
        bigquery.SchemaField("drop_off_booking_rule_id", "STRING"),
    ],
    "calendar.txt": [
        bigquery.SchemaField("service_id", "STRING"),
        bigquery.SchemaField("monday", "STRING"),
        bigquery.SchemaField("tuesday", "STRING"),
        bigquery.SchemaField("wednesday", "STRING"),
        bigquery.SchemaField("thursday", "STRING"),
        bigquery.SchemaField("friday", "STRING"),
        bigquery.SchemaField("saturday", "STRING"),
        bigquery.SchemaField("sunday", "STRING"),
        bigquery.SchemaField("start_date", "STRING"),
        bigquery.SchemaField("end_date", "STRING"),
    ],
    "shapes.txt": [
        bigquery.SchemaField("shape_id", "STRING"),
        bigquery.SchemaField("shape_pt_lat", "STRING"),
        bigquery.SchemaField("shape_pt_lon", "STRING"),
        bigquery.SchemaField("shape_pt_sequence", "STRING"),
        bigquery.SchemaField("shape_dist_traveled", "STRING"),
    ],
}

def get_expected_columns(schema: list) -> list:
    """collect columns complying with declared ordering in GTFS_SCHEMAS."""
    return [field.name for field in schema]


def validate_header(zf, filename, expected_columns):
    with zf.open(filename) as f:
        header = f.readline().decode("utf-8-sig").strip().split(",")
    if header != expected_columns:
        raise ValueError(
            f"{filename}: schema mismatch.\n"
            f"  expected: {expected_columns}\n"
            f"  got:      {header}"
        )



def materialize():
    print(f"Downloading GTFS from {GTFS_URL}")
    response = requests.get(GTFS_URL, timeout=60)
    response.raise_for_status()

    # calculate sha1 háh for the new zip
    sha1_hash = hashlib.sha1(response.content).hexdigest()

    gcs_client = storage.Client(project=GCP_PROJECT)
    bq_client = bigquery.Client(project=GCP_PROJECT)
    bucket = gcs_client.bucket(GCS_BUCKET)

    hash_blob_path = f"{GCS_PREFIX}/latest_sha1.txt"
    hash_blob = bucket.blob(hash_blob_path)

    current_sha1 = ""
    if hash_blob.exists():
        current_sha1 = hash_blob.download_as_text().strip()

    if sha1_hash == current_sha1:
        print(f"GTFS Static feed unchanged (SHA1: {sha1_hash}). Skipping ingestion.")
        return

    print(f"New GTFS Static feed detected! Previous: '{current_sha1}' -> New: '{sha1_hash}'")

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for filename, bq_table in GTFS_FILES.items():
            if filename not in zf.namelist():
                print(f"WARNING: {filename} not found in ZIP, skipping")
                continue

            # Upload to GCS
            data = zf.read(filename)
            gcs_path = f"{GCS_PREFIX}/{filename}"
            blob = bucket.blob(gcs_path)
            blob.upload_from_string(data, content_type="text/plain")
            print(f"Uploaded {filename} -> gs://{GCS_BUCKET}/{gcs_path}")

            # Load from GCS into BigQuery
            gcs_uri = f"gs://{GCS_BUCKET}/{gcs_path}"
            table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{bq_table}"

            # validate headers before uploading
            expected_columns = get_expected_columns(GTFS_SCHEMAS[filename])
            validate_header(zf, filename, expected_columns)

            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.CSV,
                skip_leading_rows=1,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                schema=GTFS_SCHEMAS[filename],
            )

            load_job = bq_client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
            load_job.result()
            print(f"Loaded {filename} -> {table_ref}")

    hash_blob.upload_from_string(sha1_hash, content_type="text/plain")
    print(f"Updated latest SHA1 hash ({sha1_hash}) to GCS.")
    print("Ingestion complete.")
materialize()