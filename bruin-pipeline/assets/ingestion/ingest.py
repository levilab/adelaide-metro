import io
import sys
import os
import zipfile
import requests
from google.cloud import bigquery, storage
from google.api_core.exceptions import NotFound, Forbidden
from dotenv import load_dotenv

load_dotenv()

GTFS_URL = "https://gtfs.adelaidemetro.com.au/v1/static/latest/google_transit.zip"
GCS_BUCKET = os.environ.get("GCS_BUCKET")
GCS_PREFIX = "gtfs_static/adelaide-metro"
GCP_PROJECT = os.environ['GCP_PROJECT']
BQ_dataset = "raw"
client = storage.Client.from_service_account_json(os.environ['GCP_CREDENTIALS'])

# map necessary file names to Big Query table names
GTFS_FILES = {
    "routes.txt": "gtfs_routes",
    "stops.txt": "gtfs_stops",
    "trips.txt": "gtfs_trips",
    "stop_times.txt": "gtfs_stop_times",
    "calendar.txt": "gtfs_calendar",
}

def download_gtfs():
    print(f"Downloading from {GTFS_URL}")
    response = requests.get(GTFS_URL, timeout=60)
    response.raise_for_status()

    return response.content

def create_bucket(bucket_name):
    try:
        # get bucket
        bucket = client.get_bucket(bucket_name)

        # check if bucket is available
        project_bucket_ids = [bkct.id for bkct in client.list_buckets()]
        if bucket_name in project_bucket_ids:
            print(
                f"Bucket {GCS_BUCKET} exists and belongs to the current project. Proceeding..."
            )
        else:
            print(
                f"Bucket {GCS_BUCKET} exists but not belong to your project."
            )
            sys.exit(1)
    except NotFound:
        # if bucket is non-existent, create it:
        bucket = client.create_bucket(bucket_name)
        print(f"Bucket {GCS_BUCKET} created")

    except Forbidden:
        # unauthorized access
        print(
            f"You are not allowed to access bucket {GCS_BUCKET}"
        )
        sys.exit(1)


def verify_GCS_upload(bucket, file):
    return storage.Blob(bucket=bucket, name=file).exists(client)

def uploaded_to_gcs():
    create_bucket(GCS_BUCKET)
    bucket = client.bucket(os.environ.get('GCS_BUCKET'))
    
    gtfs_data = download_gtfs()

    # extract the zip file directly on memory
    with zipfile.ZipFile(io.BytesIO(gtfs_data)) as zf:
        try:
            for filename, tablename in GTFS_FILES.items():
                if filename not in zf.namelist():
                    print(f"WARNING: {filename} not found in zip, skipping to the next file")
                    continue
                
                # upload to GCS
                data = zf.read(filename) # read file to memory
                gcs_path = f"{GCS_PREFIX}/{filename}"

                # use blob to push file to GCS without i/o write
                blob = bucket.blob(gcs_path)
                print(f"Uploading {filename} -> gs://{GCS_BUCKET}/{gcs_path}")
                blob.upload_from_string(data, content_type = "text/plain") 
                print(f"Uploading completed.")

                if verify_GCS_upload(filename):
                    print(f"Verification successful for {filename}")
                    return

        except Exception as e:
            print(f"Failed to upload {filename} to GCS: {e}")

if __name__ == "__main__":
    uploaded_to_gcs()