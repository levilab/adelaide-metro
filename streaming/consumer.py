import os
import sys
import time
import logging
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import pandas as pd
from confluent_kafka import Consumer, KafkaError, KafkaException
from google.cloud import bigquery
from google.transit import gtfs_realtime_pb2
from google.api_core.exceptions import (
    InternalServerError,
    ServiceUnavailable,
    GatewayTimeout,
)

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

FEED_STATUS_SCHEMA = [
    bigquery.SchemaField(
        "polled_date",
        "DATE",
        mode="REQUIRED",
    ),
    bigquery.SchemaField(
        "polled_at",
        "TIMESTAMP",
        mode="REQUIRED",
    ),
    bigquery.SchemaField(
        "feed_name",
        "STRING",
        mode="REQUIRED",
    ),
    bigquery.SchemaField(
        "feed_timestamp",
        "TIMESTAMP",
    ),
    bigquery.SchemaField(
        "entity_count",
        "INTEGER",
        mode="REQUIRED",
    ),
    bigquery.SchemaField(
        "http_success",
        "BOOLEAN",
        mode="REQUIRED",
    ),
    bigquery.SchemaField(
        "error_message",
        "STRING",
    ),
]

TRIP_UPDATES_SCHEMA = [
    bigquery.SchemaField("ingested_date", "DATE"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    bigquery.SchemaField("feed_timestamp", "TIMESTAMP"),
    bigquery.SchemaField("source_gcs_uri", "STRING"),
    bigquery.SchemaField("entity_id", "STRING"),
    bigquery.SchemaField("trip_id", "STRING"),
    bigquery.SchemaField("route_id", "STRING"),
    bigquery.SchemaField("direction_id", "INTEGER"),
    bigquery.SchemaField("start_date", "STRING"),
    bigquery.SchemaField("schedule_relationship", "STRING"),
    bigquery.SchemaField("vehicle_id", "STRING"),
    bigquery.SchemaField("vehicle_label", "STRING"),
    bigquery.SchemaField("trip_update_timestamp", "TIMESTAMP"),
    bigquery.SchemaField("stop_sequence", "INTEGER"),
    bigquery.SchemaField("stop_id", "STRING"),
    bigquery.SchemaField("arrival_time", "TIMESTAMP"),
    bigquery.SchemaField("fetched_date", "DATE"),
    bigquery.SchemaField("fetched_at", "TIMESTAMP"),
]

VEHICLE_POSITIONS_SCHEMA = [
    bigquery.SchemaField("ingested_date", "DATE"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    bigquery.SchemaField("feed_timestamp", "TIMESTAMP"),
    bigquery.SchemaField("source_gcs_uri", "STRING"),
    bigquery.SchemaField("entity_id", "STRING"),
    bigquery.SchemaField("trip_id", "STRING"),
    bigquery.SchemaField("route_id", "STRING"),
    bigquery.SchemaField("direction_id", "INTEGER"),
    bigquery.SchemaField("start_date", "STRING"),
    bigquery.SchemaField("schedule_relationship", "STRING"),
    bigquery.SchemaField("vehicle_id", "STRING"),
    bigquery.SchemaField("vehicle_label", "STRING"),
    bigquery.SchemaField("latitude", "FLOAT"),
    bigquery.SchemaField("longitude", "FLOAT"),
    bigquery.SchemaField("bearing", "FLOAT"),
    bigquery.SchemaField("speed", "FLOAT"),
    bigquery.SchemaField("vehicle_timestamp", "TIMESTAMP"),
    bigquery.SchemaField("occupancy_status", "STRING"),
    bigquery.SchemaField("fetched_date", "DATE"),
    bigquery.SchemaField("fetched_at", "TIMESTAMP"),
]

SERVICE_ALERTS_SCHEMA = [
    bigquery.SchemaField("ingested_date", "DATE"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    bigquery.SchemaField("feed_timestamp", "TIMESTAMP"),
    bigquery.SchemaField("source_gcs_uri", "STRING"),
    bigquery.SchemaField("entity_id", "STRING"),
    bigquery.SchemaField("header_text", "STRING"),
    bigquery.SchemaField("description_text", "STRING"),
    bigquery.SchemaField("url", "STRING"),
    bigquery.SchemaField("active_start", "TIMESTAMP"),
    bigquery.SchemaField("cause", "STRING"),
    bigquery.SchemaField("effect", "STRING"),
    bigquery.SchemaField("route_id", "STRING"),
    bigquery.SchemaField("fetched_date", "DATE"),
    bigquery.SchemaField("fetched_at", "TIMESTAMP"),
]

# define specific config for each topic
TOPICS_CONFIG = {
    "gtfs.vehicle_positions": {
        "table_name": "gtfs_realtime_vehicle_positions",
        "poll_timeout": 2.0,
        "schema": VEHICLE_POSITIONS_SCHEMA,     
    },
    "gtfs.trip_updates": {
        "table_name": "gtfs_realtime_trip_updates",
        "poll_timeout": 3.0,
        "schema": TRIP_UPDATES_SCHEMA,
    },
    "gtfs.service_alerts": {
        "table_name": "gtfs_realtime_service_alerts",
        "poll_timeout": 5.0,
        "schema": SERVICE_ALERTS_SCHEMA,
    },
    "gtfs.feed_status": {
        "table_name": "gtfs_feed_status",
        "poll_timeout": 2.0,
        "message_format": "json",
        "partition_field": "polled_date",
        "schema": FEED_STATUS_SCHEMA,
    },
}


def make_consumer(bootstrap_servers: str, topic_name: str) -> Consumer:
    clean_topic_name = topic_name.replace(".", "-")
    group_id = f"{CONSUMER_GROUP_PREFIX}-{clean_topic_name}"
    
    conf = {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,  # Manual commit after loading bigquery
    }
    security_protocol = os.environ.get("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    sasl_username = os.environ.get("KAFKA_SASL_USERNAME")
    sasl_password = os.environ.get("KAFKA_SASL_PASSWORD")

    if sasl_username and sasl_password:
        conf.update({
            "security.protocol": security_protocol,
            "sasl.mechanism": os.environ.get("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256"),
            "sasl.username": sasl_username,
            "sasl.password": sasl_password,
            "ssl.ca.location": "/app/ca.pem",
        })
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

def parse_feed_status(value: bytes) -> dict:
    payload = json.loads(value.decode("utf-8"))

    polled_at = datetime.fromisoformat(payload["polled_at"])

    if polled_at.utcoffset() is None:
        raise ValueError("polled_at must include a timezone")

    feed_timestamp = payload.get("feed_timestamp")

    return {
        "polled_date": polled_at.date(),
        "polled_at": polled_at,
        "feed_name": payload["feed_name"],
        "feed_timestamp": epoch_to_adelaide_datetime(
            feed_timestamp
        ),
        "entity_count": int(payload["entity_count"]),
        "http_success": payload["http_success"],
        "error_message": payload.get("error_message"),
    }

def parse_entity_to_rows(topic: str, entity: gtfs_realtime_pb2.FeedEntity, headers: dict) -> list[dict]:
    fetched_at_str  = (
        headers.get("fetched_at")
        or headers.get("fetch_time_adelaide")
    )
    fetched_at  = datetime.fromisoformat(fetched_at_str) if fetched_at_str else datetime.now(ADELAIDE_TZ)
    fetched_date  = fetched_at.date()
    
    feed_timestamp = int(headers.get("feed_timestamp", 0)) if headers.get("feed_timestamp") else None
    feed_dt = epoch_to_adelaide_datetime(feed_timestamp)

    base_info = {
        "fetched_date": fetched_date,
        "fetched_at": fetched_at,
        # Keep these aliases until the raw BigQuery tables are rebuilt with
        # fetched_date as their partition field.
        "ingested_date": fetched_date,
        "ingested_at": fetched_at,
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
                "schedule_relationship": gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(trip.schedule_relationship) if trip.HasField("schedule_relationship") else None,
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
            "schedule_relationship": gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(trip.schedule_relationship) if trip.HasField("schedule_relationship") else None,
            "vehicle_id": veh.id if veh.id else None,
            "vehicle_label": veh.label if veh.label else None,
            "latitude": pos.latitude if pos.HasField("latitude") else None,
            "longitude": pos.longitude if pos.HasField("longitude") else None,
            "bearing": pos.bearing if pos.HasField("bearing") else None,
            "speed": pos.speed if pos.HasField("speed") else None,
            "vehicle_timestamp": epoch_to_adelaide_datetime(vp.timestamp) if vp.timestamp else None,
            "occupancy_status": gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Name(vp.occupancy_status) if vp.HasField("occupancy_status") else None,
        })

    # PARSE SERVICE ALERTS
    elif topic == "gtfs.service_alerts" and entity.HasField("alert"):
        alert = entity.alert
        active_starts = [period.start for period in alert.active_period if period.start]

        header_txt = first_translation(alert.header_text)
        desc_txt = first_translation(alert.description_text)
        url_txt = first_translation(alert.url)
        act_start = epoch_to_adelaide_datetime(min(active_starts)) if active_starts else None
        cause_val = gtfs_realtime_pb2.Alert.Cause.Name(alert.cause) if alert.HasField("cause") else None
        effect_val = gtfs_realtime_pb2.Alert.Effect.Name(alert.effect) if alert.HasField("effect") else None

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

def should_flush_batch(
    row_count: int,
    elapsed_seconds: float,
    max_rows: int = 5000,
    max_wait_seconds: float = 30.0,
) -> bool:
    if row_count == 0:
        return False

    return (
        row_count >= max_rows
        or elapsed_seconds >= max_wait_seconds
    )

def load_batch_to_bigquery(
    bq_client: bigquery.Client,
    table_name: str,
    rows: list[dict],
    partition_field: str = "ingested_date",
    schema: list[bigquery.SchemaField] | None = None,
):
    if not rows:
        return

    df = pd.DataFrame(rows)
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{table_name}"

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        autodetect=schema is None,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=partition_field,
        ),
    )
    load_job = bq_client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    load_job.result()
    logger.info(f"[{table_name}] Loaded {len(df)} rows into BigQuery")


def process_topic_consumer(topic: str, config: dict):
    consumer = make_consumer(KAFKA_BOOTSTRAP_SERVERS, topic)
    bq_client = bigquery.Client(project=GCP_PROJECT)

    consumer.subscribe([topic])
    logger.info(f"Worker started consuming topic '{topic}'")

    buffer_rows = []
    batch_started_at = None

    try:
        while True:
            msg = consumer.poll(timeout=config["poll_timeout"])

            if msg is not None:
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        raise KafkaException(msg.error())
                else:
                    if config.get("message_format") == "json":
                        parsed_rows = [
                            parse_feed_status(msg.value())
                        ]
                    else:
                        headers = parse_kafka_headers(msg.headers())
                        entity = gtfs_realtime_pb2.FeedEntity()
                        entity.ParseFromString(msg.value())

                        parsed_rows = parse_entity_to_rows(
                            topic, entity, headers
                        )

                    if parsed_rows and not buffer_rows:
                        batch_started_at = time.monotonic()

                    buffer_rows.extend(parsed_rows)

            if not buffer_rows:
                continue

            elapsed_seconds = (
                time.monotonic() - batch_started_at
            )

            if msg is None or should_flush_batch(
                row_count=len(buffer_rows),
                elapsed_seconds=elapsed_seconds,
            ):
                logger.info(
                    "[%s] Flushing %s rows after %.1f seconds",
                    topic,
                    len(buffer_rows),
                    elapsed_seconds,
                )

                load_batch_to_bigquery(
                    bq_client=bq_client,
                    table_name=config["table_name"],
                    rows=buffer_rows,
                    partition_field=config.get(
                        "partition_field",
                        "ingested_date",
                    ),
                    schema=config.get("schema"),
                )

                consumer.commit(asynchronous=False)

                buffer_rows = []
                batch_started_at = None

    except Exception as e:
        logger.exception(
            "[%s] Consumer worker failed",
            topic,
        )
        raise
    finally:
        consumer.close()
        logger.info(
            "[%s] Consumer connection closed",
            topic,
        )

def run_topic_worker(topic: str, config: dict):
    while True:
        try:
            process_topic_consumer(topic, config)

        except (
            InternalServerError,
            ServiceUnavailable,
            GatewayTimeout,
        ):
            logger.warning(
                "[%s] Temporary BigQuery failure. "
                "Restarting consumer in 5 seconds.",
                topic,
            )
            time.sleep(5)

        else:
            raise RuntimeError(
                f"[{topic}] Consumer returned unexpectedly"
            )

def main():
    logger.info("Starting Multi-threaded GTFS Consumer Framework...")

    # Run one worker for each configured topic.
    with ThreadPoolExecutor(max_workers=len(TOPICS_CONFIG)) as executor:
        for topic, config in TOPICS_CONFIG.items():
            executor.submit(run_topic_worker, topic, config)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received for Consumers...")


if __name__ == "__main__":
    main()
