import os
import sys
import time
import logging
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import requests
from confluent_kafka import Producer
from google.transit import gtfs_realtime_pb2

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gtfs-producer")

ADELAIDE_TZ = ZoneInfo("Australia/Adelaide")
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
FEED_STATUS_TOPIC = os.environ.get(
    "FEED_STATUS_TOPIC",
    "gtfs.feed_status",
)
HEADERS = {"accept": "application/x-google-protobuf"}

FEEDS_CONFIG = {
    "vehicle_positions": {
        "url": "https://gtfs.adelaidemetro.com.au/v1/realtime/vehicle_positions",
        "topic": "gtfs.vehicle_positions",
        "interval": 15,  # 15 secs
    },
    "trip_updates": {
        "url": "https://gtfs.adelaidemetro.com.au/v1/realtime/trip_updates",
        "topic": "gtfs.trip_updates",
        "interval": 60,  # 60 secs
    },
    "service_alerts": {
        "url": "https://gtfs.adelaidemetro.com.au/v1/realtime/service_alerts",
        "topic": "gtfs.service_alerts",
        "interval": 300,  # 300 secs
    },
}


def make_producer(bootstrap_servers: str) -> Producer:
    conf = {
        "bootstrap.servers": bootstrap_servers,
        "client.id": "gtfs-realtime-producer",
        "acks": "all",
        "compression.type": "snappy",
        "linger.ms": 20,
        "queue.buffering.max.messages": 100000,
        "queue.buffering.max.kbytes": 102400,
        "retries": 5,
        "retry.backoff.ms": 500,
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
        
    logger.info(f"Initializing Kafka Producer connected to {bootstrap_servers}")
    return Producer(conf)


def delivery_report(err, msg):
    if err is not None:
        logger.error(f"Failed to deliver msg to {msg.topic()} [{msg.key()}]: {err}")


def fetch_feed(feed_name: str, url: str) -> tuple[gtfs_realtime_pb2.FeedMessage, str]:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    fetched_at = datetime.now(ADELAIDE_TZ).isoformat()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    return feed, fetched_at


def extract_entity_key(entity: gtfs_realtime_pb2.FeedEntity) -> str:
    if entity.HasField("vehicle") and entity.vehicle.vehicle.id:
        return f"vehicle_{entity.vehicle.vehicle.id}"
    elif entity.HasField("trip_update") and entity.trip_update.trip.trip_id:
        return f"trip_{entity.trip_update.trip.trip_id}"
    return entity.id


def publish_event(
    producer: Producer,
    topic: str,
    entity: gtfs_realtime_pb2.FeedEntity,
    feed_timestamp: int,
    fetched_at: str,
):
    key = extract_entity_key(entity)
    payload = entity.SerializeToString() # transform to raw bytes, so any languagues can read it
    headers = [
        ("fetched_at", fetched_at.encode("utf-8")),
        # Keep the legacy header during the rolling deployment so that the
        # previous consumer revision can still read newly produced messages.
        ("fetch_time_adelaide", fetched_at.encode("utf-8")),
        ("feed_timestamp", str(feed_timestamp).encode("utf-8")),
    ]

    producer.produce(
        topic=topic,
        key=key.encode("utf-8"),
        value=payload,
        headers=headers,
        on_delivery=delivery_report,
    )

def publish_feed_status(
    producer: Producer,
    feed_name: str,
    polled_at: str,
    feed_timestamp: int | None,
    entity_count: int,
    http_success: bool,
    error_message: str | None = None,
):
    payload = {
        "feed_name": feed_name,
        "polled_at": polled_at,
        "feed_timestamp": feed_timestamp,
        "entity_count": entity_count,
        "http_success": http_success,
        "error_message": error_message,
    }

    producer.produce(
        topic=FEED_STATUS_TOPIC,
        key=feed_name.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
        on_delivery=delivery_report,
    )

def process_feed(producer: Producer, feed_name: str, config: dict):
    # Indepdendent worker for each feed
    logger.info(f"Started worker thread for {feed_name} (Interval: {config['interval']}s)")

    while True:
        start_time = time.time()
        try:
            feed, fetched_at = fetch_feed(feed_name, config["url"])
            feed_timestamp = feed.header.timestamp
            topic = config["topic"]

            count = 0
            for entity in feed.entity:
                publish_event(producer, topic, entity, feed_timestamp, fetched_at)
                count += 1
                # Poll  internal events from producer every 500 msgs to avoid out of memory
                if count % 500 == 0:
                    producer.poll(0)

            publish_feed_status(
                producer=producer,
                feed_name=feed_name,
                polled_at=fetched_at,
                feed_timestamp=feed_timestamp,
                entity_count=count,
                http_success=True,
            )
            # flush all remaining messages in internal RAM queue
            remaining = producer.flush(timeout=5) 
            if remaining:
                logger.warning("%s messages still pending", remaining)
            logger.info(f"[{feed_name}] Published {count} entities to '{topic}'")

        except requests.RequestException as e:
            logger.error(f"[{feed_name}] Network Error: {e}")

            try:
                publish_feed_status(
                    producer=producer,
                    feed_name=feed_name,
                    polled_at=datetime.now(ADELAIDE_TZ).isoformat(),
                    feed_timestamp=None,
                    entity_count=0,
                    http_success=False,
                    error_message=str(e),
                )
                producer.flush(timeout=5)
            except Exception as status_error:
                logger.error(
                    f"[{feed_name}] Failed to publish feed status: "
                    f"{status_error}"
                )
        except Exception as e:
            logger.error(f"[{feed_name}] Unexpected Error: {e}", exc_info=True)

        elapsed = time.time() - start_time
        sleep_time = max(0.0, config["interval"] - elapsed)
        time.sleep(sleep_time)


def main():
    producer = make_producer(KAFKA_BOOTSTRAP_SERVERS)

    with ThreadPoolExecutor(max_workers=len(FEEDS_CONFIG)) as executor:
        for feed_name, config in FEEDS_CONFIG.items():
            executor.submit(process_feed, producer, feed_name, config)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received...")
    finally:
        logger.info("Flushing producer buffer...")
        producer.flush(timeout=10)
        logger.info("Producer stopped gracefully.")


if __name__ == "__main__":
    main()
