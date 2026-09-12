import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import pandas as pd
from confluent_kafka import Consumer, KafkaError, KafkaException
from google.cloud import bigquery
from google.transit import gtfs_realtime_pb2

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gtfs-consumer")

ADELAIDE_TZ = ZoneInfo("Australia/Adelaide")
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CONSUMER_GROUP_PREFIX = os.environ.get("CONSUMER_GROUP_PREFIX", "gtfs-bq-loader")

GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "adelaide-metro-505702")
BQ_DATASET = os.environ.get("BQ_DATASET", "streaming")

# define specific config for each topic
TOPICS_CONFIG = {
    "gtfs.vehicle_positions": {
        "table_name": "gtfs_realtime_vehicle_positions",
        "poll_timeout": 2.0,     
    },
    "gtfs.trip_updates": {
        "table_name": "gtfs_realtime_trip_updates",
        "poll_timeout": 3.0,
    },
    "gtfs.service_alerts": {
        "table_name": "gtfs_realtime_service_alerts",
        "poll_timeout": 5.0,
    },
}


def make_consumer(bootstrap_servers: str, topic_name: str) -> Consumer:
    """Tạo Consumer riêng biệt cho từng Topic với Group ID độc lập."""
    clean_topic_name = topic_name.replace(".", "-")
    group_id = f"{CONSUMER_GROUP_PREFIX}-{clean_topic_name}"
    
    conf = {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,  # Manual commit after loading bigquery
    }
    logger.info(f"Initializing Consumer for topic '{topic_name}' with Group ID '{group_id}'")
    return Consumer(conf)


def epoch_to_adelaide_datetime(epoch_seconds: int):
    if not epoch_seconds:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=ADELAIDE_TZ)


def gtfs_date_to_string(date_value: str):
    if not date_value:
        return None
    return f"{date_value[:4]}-{date_value[4:6]}-{date_value[6:8]}"


def first_translation(translated_string):
    if not translated_string or not translated_string.translation:
        return None
    return translated_string.translation[0].text or None


def parse_kafka_headers(headers: list) -> dict:
    parsed = {}
    if headers:
        for k, v in headers:
            parsed[k] = v.decode("utf-8") if v else None
    return parsed


def parse_entity_to_rows(topic: str, entity: gtfs_realtime_pb2.FeedEntity, headers: dict) -> list[dict]:
    fetch_time_str = headers.get("fetch_time_adelaide")
    ingested_at = datetime.fromisoformat(fetch_time_str) if fetch_time_str else datetime.now(ADELAIDE_TZ)
    ingested_date = ingested_at.date()
    
    feed_timestamp = int(headers.get("feed_timestamp", 0)) if headers.get("feed_timestamp") else None
    feed_dt = epoch_to_adelaide_datetime(feed_timestamp)

    base_info = {
        "ingested_date": ingested_date,
        "ingested_at": ingested_at,
        "feed_timestamp": feed_dt,
        "source_gcs_uri": "kafka_stream",
    }

    rows = []

    # PARSE TRIP UPDATES
    if topic == "gtfs.trip_updates" and entity.HasField("trip_update"):
        tu = entity.trip_update
        trip = tu.trip
        vehicle = tu.vehicle

        for stop_update in tu.stop_time_update:
            rows.append({
                **base_info,
                "entity_id": entity.id,
                "trip_id": trip.trip_id if trip.trip_id else None,
                "route_id": trip.route_id if trip.route_id else None,
                "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
                "start_date": gtfs_date_to_string(trip.start_date) if trip.start_date else None,
                "schedule_relationship": str(trip.schedule_relationship) if trip.HasField("schedule_relationship") else None,
                "vehicle_id": vehicle.id if vehicle.id else None,
                "vehicle_label": vehicle.label if vehicle.label else None,
                "trip_update_timestamp": epoch_to_adelaide_datetime(tu.timestamp) if tu.timestamp else None,
                "stop_sequence": stop_update.stop_sequence if stop_update.HasField("stop_sequence") else None,
                "stop_id": stop_update.stop_id if stop_update.stop_id else None,
                "arrival_time": epoch_to_adelaide_datetime(stop_update.arrival.time) if stop_update.HasField("arrival") and stop_update.arrival.time else None,
            })

    # PARSE VEHICLE POSITIONS
    elif topic == "gtfs.vehicle_positions" and entity.HasField("vehicle"):
        vp = entity.vehicle
        trip = vp.trip
        pos = vp.position
        veh = vp.vehicle

        rows.append({
            **base_info,
            "entity_id": entity.id,
            "trip_id": trip.trip_id if trip.trip_id else None,
            "route_id": trip.route_id if trip.route_id else None,
            "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
            "start_date": gtfs_date_to_string(trip.start_date) if trip.start_date else None,
            "schedule_relationship": str(trip.schedule_relationship) if trip.HasField("schedule_relationship") else None,
            "vehicle_id": veh.id if veh.id else None,
            "vehicle_label": veh.label if veh.label else None,
            "latitude": pos.latitude if pos.HasField("latitude") else None,
            "longitude": pos.longitude if pos.HasField("longitude") else None,
            "bearing": pos.bearing if pos.HasField("bearing") else None,
            "speed": pos.speed if pos.HasField("speed") else None,
            "vehicle_timestamp": epoch_to_adelaide_datetime(vp.timestamp) if vp.timestamp else None,
        })

    # PARSE SERVICE ALERTS
    elif topic == "gtfs.service_alerts" and entity.HasField("alert"):
        alert = entity.alert
        active_starts = [period.start for period in alert.active_period if period.start]

        header_txt = first_translation(alert.header_text)
        desc_txt = first_translation(alert.description_text)
        url_txt = first_translation(alert.url)
        act_start = epoch_to_adelaide_datetime(min(active_starts)) if active_starts else None
        cause_val = str(alert.cause) if alert.HasField("cause") else None
        effect_val = str(alert.effect) if alert.HasField("effect") else None

        if alert.informed_entity:
            for item in alert.informed_entity:
                rows.append({
                    **base_info,
                    "entity_id": entity.id,
                    "header_text": header_txt,
                    "description_text": desc_txt,
                    "url": url_txt,
                    "active_start": act_start,
                    "cause": cause_val,
                    "effect": effect_val,
                    "route_id": item.route_id if item.route_id else None,
                })
        else:
            rows.append({
                **base_info,
                "entity_id": entity.id,
                "header_text": header_txt,
                "description_text": desc_txt,
                "url": url_txt,
                "active_start": act_start,
                "cause": cause_val,
                "effect": effect_val,
                "route_id": None,
            })

    return rows


def load_batch_to_bigquery(bq_client: bigquery.Client, table_name: str, rows: list[dict]):
    if not rows:
        return

    df = pd.DataFrame(rows)
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
    logger.info(f"[{table_name}] Loaded {len(df)} rows into BigQuery")


def process_topic_consumer(topic: str, config: dict):
    """Worker Consumer nạp TOÀN BỘ dữ liệu của mỗi đợt poll vào BigQuery."""
    consumer = make_consumer(KAFKA_BOOTSTRAP_SERVERS, topic)
    bq_client = bigquery.Client(project=GCP_PROJECT)

    consumer.subscribe([topic])
    logger.info(f"Worker started consuming topic '{topic}'")

    buffer_rows = []

    try:
        while True:
            # Poll data from Kafka
            msg = consumer.poll(timeout=config["poll_timeout"])

            # if kafka returns None (no more data) -> Flush all buffer to BQ
            if msg is None:
                if buffer_rows:
                    logger.info(f"[{topic}] End of current batch. Flushing ALL {len(buffer_rows)} rows to BigQuery...")
                    load_batch_to_bigquery(bq_client, config["table_name"], buffer_rows)
                    buffer_rows = []  # Reset buffer
                    consumer.commit(asynchronous=False)  # Commit offset after loading to BQ
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error(f"[{topic}] Kafka Error: {msg.error()}")
                    raise KafkaException(msg.error())

            # Parse messages and append to buffer
            headers = parse_kafka_headers(msg.headers())
            entity = gtfs_realtime_pb2.FeedEntity()
            entity.ParseFromString(msg.value())

            parsed_rows = parse_entity_to_rows(topic, entity, headers)
            buffer_rows.extend(parsed_rows)

    except Exception as e:
        logger.error(f"[{topic}] Worker failed unexpectedly: {e}", exc_info=True)
    finally:
        # Flush remaining buffer after stopping application.
        if buffer_rows:
            load_batch_to_bigquery(bq_client, config["table_name"], buffer_rows)
            consumer.commit(asynchronous=False)
        consumer.close()
        logger.info(f"[{topic}] Consumer worker shut down.")

def main():
    logger.info("Starting Multi-threaded GTFS Consumer Framework...")

    # running 3 workers in parallel
    with ThreadPoolExecutor(max_workers=len(TOPICS_CONFIG)) as executor:
        for topic, config in TOPICS_CONFIG.items():
            executor.submit(process_topic_consumer, topic, config)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received for Consumers...")


if __name__ == "__main__":
    main()