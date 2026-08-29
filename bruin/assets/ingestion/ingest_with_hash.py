import hashlib
import io
import os
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests
from google.cloud import bigquery, storage

GTFS_URL = "https://gtfs.adelaidemetro.com.au/v1/static/latest/google_transit.zip"
GCS_BUCKET = os.environ.get("GCS_BUCKET")
GCP_PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
BQ_DATASET = "raw"
VERSION_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.gtfs_feed_versions"

GTFS_FILES = {
    "routes.txt": "gtfs_routes",
    "stops.txt": "gtfs_stops",
    "trips.txt": "gtfs_trips",
    "stop_times.txt": "gtfs_stop_times",
    "calendar.txt": "gtfs_calendar",
}


def compute_core_hash(zip_file: zipfile.ZipFile) -> str:
    """Tính SHA256 tổng hợp dựa trên nội dung 5 file lõi trong ZIP."""
    hasher = hashlib.sha256()
    for filename in sorted(GTFS_FILES.keys()):
        if filename in zip_file.namelist():
            with zip_file.open(filename) as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
    return hasher.hexdigest()


def ensure_version_table_exists(bq_client: bigquery.Client):
    """Khởi tạo bảng quản lý feed_versions nếu chưa có."""
    schema = [
        bigquery.SchemaField("feed_version_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("core_hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("valid_from", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("valid_to", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(VERSION_TABLE, schema=schema)
    bq_client.create_table(table, exists_ok=True)


def get_latest_active_hash(bq_client: bigquery.Client) -> str:
    """Lấy core_hash của version đang active trong BQ."""
    query = f"""
        SELECT core_hash 
        FROM `{VERSION_TABLE}` 
        WHERE valid_to = '9999-12-31' 
        ORDER BY created_at DESC 
        LIMIT 1
    """
    query_job = bq_client.query(query)
    results = list(query_job.result())
    return results[0].core_hash if results else None


def update_feed_versions(bq_client: bigquery.Client, new_version_id: str, new_hash: str, today_str: str):
    """Đóng version cũ (valid_to = today - 1) và insert version mới (valid_from = today, valid_to = 9999-12-31)."""
    # 1. Đóng version cũ
    close_query = f"""
        UPDATE `{VERSION_TABLE}`
        SET valid_to = DATE_SUB(DATE('{today_str}'), INTERVAL 1 DAY)
        WHERE valid_to = '9999-12-31'
    """
    bq_client.query(close_query).result()

    # 2. Tạo version mới
    insert_query = f"""
        INSERT INTO `{VERSION_TABLE}` (feed_version_id, core_hash, valid_from, valid_to, created_at)
        VALUES ('{new_version_id}', '{new_hash}', DATE('{today_str}'), DATE('9999-12-31'), CURRENT_TIMESTAMP())
    """
    bq_client.query(insert_query).result()


def main():
    bq_client = bigquery.Client(project=GCP_PROJECT)
    gcs_client = storage.Client(project=GCP_PROJECT)
    bucket = gcs_client.bucket(GCS_BUCKET)

    ensure_version_table_exists(bq_client)

    print(f"Downloading GTFS from {GTFS_URL}")
    response = requests.get(GTFS_URL, timeout=60)
    response.raise_for_status()

    zip_bytes = io.BytesIO(response.content)

    with zipfile.ZipFile(zip_bytes) as zf:
        current_hash = compute_core_hash(zf)
        print(f"Computed Core Hash: {current_hash}")

        latest_hash = get_latest_active_hash(bq_client)

        # Trùng Hash => Không có thay đổi về lịch trình -> Dừng pipeline
        if current_hash == latest_hash:
            print("No changes detected in GTFS core files. Skipping ingestion.")
            return

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        version_id = f"v_{today_str.replace('-', '')}_{current_hash[:8]}"
        now_ts = datetime.now(timezone.utc)

        print(f"New schedule version detected! Initializing load for version: {version_id}")

        for filename, bq_table in GTFS_FILES.items():
            if filename not in zf.namelist():
                print(f"WARNING: {filename} not found in ZIP, skipping")
                continue

            # 1. Upload file raw lên GCS theo folder version
            data = zf.read(filename)
            gcs_path = f"gtfs_static/adelaide-metro/{version_id}/{filename}"
            blob = bucket.blob(gcs_path)
            blob.upload_from_string(data, content_type="text/plain")
            print(f"Uploaded -> gs://{GCS_BUCKET}/{gcs_path}")

            # 2. Đọc CSV bằng Pandas để append thêm metadata cột version
            df = pd.read_csv(io.BytesIO(data), dtype=str)
            df["feed_version_id"] = version_id
            df["ingested_at"] = now_ts

            # 3. Load vào BigQuery bằng WRITE_APPEND (SCD Type 2 Raw)
            table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{bq_table}"
            job_config = bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                autodetect=True,
            )

            load_job = bq_client.load_table_from_dataframe(df, table_ref, job_config=job_config)
            load_job.result()
            print(f"Appended {len(df)} rows to {table_ref} with feed_version_id={version_id}")

        # 4. Cập nhật thông tin version mới vào bảng metadata
        update_feed_versions(bq_client, version_id, current_hash, today_str)
        print(f"Successfully updated {VERSION_TABLE} with version {version_id}.")


main()