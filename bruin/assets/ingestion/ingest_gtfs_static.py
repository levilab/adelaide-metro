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
    ]
}


def materialize():
    print(f"Downloading GTFS from {GTFS_URL}")
    response = requests.get(GTFS_URL, timeout=60)
    response.raise_for_status()

    gcs_client = storage.Client(project=GCP_PROJECT)
    bq_client = bigquery.Client(project=GCP_PROJECT)
    bucket = gcs_client.bucket(GCS_BUCKET)

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

            job_config_kwargs = {
                "source_format": bigquery.SourceFormat.CSV,
                "skip_leading_rows": 1,
                "write_disposition": bigquery.WriteDisposition.WRITE_TRUNCATE,
            }

            if filename in GTFS_SCHEMAS:
                job_config_kwargs["schema"] = GTFS_SCHEMAS[filename]
            else:
                job_config_kwargs["autodetect"] = True

            job_config = bigquery.LoadJobConfig(**job_config_kwargs)

            load_job = bq_client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
            load_job.result()
            print(f"Loaded {filename} -> {table_ref}")

    print("Ingestion complete.")
materialize()