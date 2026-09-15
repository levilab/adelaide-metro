import os
import sys
import time
import logging
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

    fetch_time = datetime.now(ADELAIDE_TZ).isoformat()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    return feed, fetch_time


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
    fetch_time: str,
):
    key = extract_entity_key(entity)
    payload = entity.SerializeToString() # transform to raw bytes, so any languagues can read it
    headers = [
        ("fetch_time_adelaide", fetch_time.encode("utf-8")),
        ("feed_timestamp", str(feed_timestamp).encode("utf-8")),
    ]

    producer.produce(
        topic=topic,
        key=key.encode("utf-8"),
        value=payload,
        headers=headers,
        on_delivery=delivery_report,
    )


def process_feed(producer: Producer, feed_name: str, config: dict):
    """Worker loop độc lập cho từng feed dựa theo polling interval riêng."""
    logger.info(f"Started worker thread for {feed_name} (Interval: {config['interval']}s)")

    while True:
        start_time = time.time()
        try:
            feed, fetch_time = fetch_feed(feed_name, config["url"])
            feed_timestamp = feed.header.timestamp
            topic = config["topic"]

            count = 0
            for entity in feed.entity:
                publish_event(producer, topic, entity, feed_timestamp, fetch_time)
                count += 1
                # Poll  internal events from producer every 500 msgs to avoid out of memory
                if count % 500 == 0:
                    producer.poll(0)

            producer.flush(timeout=5)
            logger.info(f"[{feed_name}] Published {count} entities to '{topic}'")

        except requests.RequestException as e:
            logger.error(f"[{feed_name}] Network Error: {e}")
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