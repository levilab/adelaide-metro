"""@bruin
name: raw.geo_lgas
type: python
@bruin"""

import hashlib
import io
import os
import zipfile
import geopandas as gpd
import requests
from shapely.ops import orient
from shapely.validation import make_valid
from google.cloud import bigquery, storage

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "adelaide-metro-505702")
DATASET_ID = "staging"
TABLE_ID = "stg_lgas"
GCS_BUCKET  = os.environ.get("GCS_BUCKET", "adelaide-metro-505702-raw")
GCS_PREFIX = "geo_lgas"

# URL ZIP chứa ranh giới LGA từ DPTI SA Data Portal
ZIP_URL = "https://www.dptiapps.com.au/dataportal/LGA_geojson.zip"
TARGET_FILE = "LGA_GDA2020.geojson"

def fix_geometry_for_bigquery(geom):
    """Sửa lỗi polygon bị tự cắt và chuẩn hóa Winding Order cho BigQuery Spherical GEOGRAPHY."""
    if geom is None or geom.is_empty:
        return None

    # 1. Sửa lỗi đỉnh lặp / self-intersection bằng make_valid
    valid_geom = make_valid(geom)

    # 2. Ép chiều quay Polygon (Counter-Clockwise) để BigQuery không bị ngược quả cầu
    try:
        return orient(valid_geom, sign=1.0)
    except Exception:
        return valid_geom


def materialize():
    print(f"⏳ Downloading DPTI LGA ZIP feed from {ZIP_URL}")
    response = requests.get(ZIP_URL, timeout=60)
    response.raise_for_status()

    # 1. Check SHA1 hash trên GCS để skip ingestion nếu không có thay đổi
    sha1_hash = hashlib.sha1(response.content).hexdigest()

    gcs_client = storage.Client(project=PROJECT_ID)
    bq_client = bigquery.Client(project=PROJECT_ID)
    bucket = gcs_client.bucket(GCS_BUCKET)

    hash_blob_path = f"{GCS_PREFIX}/latest_sha1.txt"
    hash_blob = bucket.blob(hash_blob_path)

    current_sha1 = ""
    if hash_blob.exists():
        current_sha1 = hash_blob.download_as_text().strip()

    if sha1_hash == current_sha1:
        print(f"✅ ZIP feed unchanged (SHA1: {sha1_hash}). Skipping ingestion.")
        return

    print(f"🔔 New ZIP feed detected! Previous: '{current_sha1}' -> New: '{sha1_hash}'")

    # 2. Giải nén ZIP trong bộ nhớ (Memory)
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        print(f"📄 Extracting '{TARGET_FILE}'...")
        geojson_bytes = z.read(TARGET_FILE)

    # 3. Đọc GeoJSON vào GeoPandas
    gdf = gpd.read_file(io.BytesIO(geojson_bytes))

    # Chuyển hệ tọa độ sang WGS84 (EPSG:4326) chuẩn của BigQuery GEOGRAPHY
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # 4. Fix geometry Winding Order & Polygon lỗi trực tiếp trên RAM
    print("🛠️ Fixing geometry Winding Order & invalid polygons...")
    gdf["geometry"] = gdf["geometry"].apply(fix_geometry_for_bigquery)

    # Chuyển sang WKT string
    gdf["polygon_geom"] = gdf["geometry"].apply(
        lambda x: x.wkt if x and not x.is_empty else None
    )
    gdf = gdf.dropna(subset=["polygon_geom"])

    # Lấy cột 'abbname' (ADELAIDE, UNLEY...) và chuẩn hóa Title Case (Adelaide, Unley...)
    lga_col = "abbname" if "abbname" in gdf.columns else "lga"
    print(f"👉 Using column '{lga_col}' for LGA Name.")
    gdf["lga_name"] = gdf[lga_col].astype(str).str.title()

    gdf_bq = gdf[["lga_name", "polygon_geom"]]

    # 5. Load vào BigQuery với schema lga_name và polygon_geom
    print("⏳ Uploading cleaned LGA data to BigQuery...")
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("lga_name", "STRING"),
            bigquery.SchemaField("polygon_geom", "GEOGRAPHY"),
        ],
    )

    job = bq_client.load_table_from_dataframe(gdf_bq, table_ref, job_config=job_config)
    job.result()

    # 6. Cập nhật Hash mới lên GCS
    hash_blob.upload_from_string(sha1_hash, content_type="text/plain")
    print(f"🎉 SUCCESS! Table loaded cleanly to BigQuery: {table_ref}")


materialize()