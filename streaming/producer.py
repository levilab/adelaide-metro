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

# Cấu hình độc lập cho từng Feed dựa trên Tần suất & Payload Size thực tế
FEEDS_CONFIG = {
    "vehicle_positions": {
        "url": "https://gtfs.adelaidemetro.com.au/v1/realtime/vehicle_positions",
        "topic": "gtfs.vehicle_positions",
        "interval": 15,  # 15 giây
    },
    "trip_updates": {
        "url": "https://gtfs.adelaidemetro.com.au/v1/realtime/trip_updates",
        "topic": "gtfs.trip_updates",
        "interval": 60,  # 60 giây
    },
    "service_alerts": {
        "url": "https://gtfs.adelaidemetro.com.au/v1/realtime/service_alerts",
        "topic": "gtfs.service_alerts",
        "interval": 300,  # 5 phút (300 giây)
    },
}


def make_producer(bootstrap_servers: str) -> Producer:
    conf = {
        "bootstrap.servers": bootstrap_servers,
        "client.id": "gtfs-realtime-producer",
        "acks": "all",
        "compression.type": "snappy",  # Nén snappy rất hiệu quả cho file trip_updates 1.6MB
        "linger.ms": 20,
        # Tăng queue memory để tránh nghẽn RAM khi parse batch 1.6MB của trip_updates
        "queue.buffering.max.messages": 100000,
        "queue.buffering.max.kbytes": 102400,  # 100MB RAM buffer
        "retries": 5,
        "retry.backoff.ms": 500,
    }
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
                # Poll nhẹ internal events của producer mỗi 500 msgs để tránh tràn bộ đệm
                if count % 500 == 0:
                    producer.poll(0)

            # Flush chỉ áp dụng cho bộ đệm của topic hiện tại
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

    # Chạy song song 3 worker thread riêng biệt cho 3 feed
    with ThreadPoolExecutor(max_workers=len(FEEDS_CONFIG)) as executor:
        for feed_name, config in FEEDS_CONFIG.items():
            executor.submit(process_feed, producer, feed_name, config)

    # Giữ main process chạy
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