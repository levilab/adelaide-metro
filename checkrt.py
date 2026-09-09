import time
from google.cloud import bigquery

client = bigquery.Client(project="adelaide-metro-505702")

query = """
SELECT 
    'vehicle_positions' AS dataset,
    COUNT(*) AS total_rows,
    MAX(ingested_at) AS latest_ingest,
    TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(ingested_at), SECOND) AS lag_seconds
FROM `adelaide-metro-505702.streaming.gtfs_realtime_vehicle_positions`
UNION ALL
SELECT 
    'trip_updates' AS dataset,
    COUNT(*) AS total_rows,
    MAX(ingested_at) AS latest_ingest,
    TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(ingested_at), SECOND) AS lag_seconds
FROM `adelaide-metro-505702.streaming.gtfs_realtime_trip_updates`
UNION ALL
SELECT 
    'service_alerts' AS dataset,
    COUNT(*) AS total_rows,
    MAX(ingested_at) AS latest_ingest,
    TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(ingested_at), SECOND) AS lag_seconds
FROM `adelaide-metro-505702.streaming.gtfs_realtime_service_alerts`
"""

print("Monitoring Live Pipeline (Press Ctrl+C to stop)...")
prev_counts = {}

while True:
    df = client.query(query).to_dataframe()
    print("\n--- " + time.strftime("%H:%M:%S") + " ---")
    
    for _, row in df.iterrows():
        name = row['dataset']
        total = row['total_rows']
        diff = total - prev_counts.get(name, total)
        prev_counts[name] = total
        
        print(f"[{name:<17}] Total: {total:>8,} | New (+): {diff:>6,} | Lag: {row['lag_seconds']}s | Latest: {row['latest_ingest'].strftime('%H:%M:%S')}")
    
    time.sleep(15) # Poll trùng với chu kỳ vehicle_positions