# 🚌 Adelaide Transit Pulse

[![Bruin](https://img.shields.io/badge/Orchestration-Bruin-F97316?style=flat-square)]()
[![BigQuery](https://img.shields.io/badge/Warehouse-BigQuery-4285F4?style=flat-square&logo=googlebigquery&logoColor=white)]()
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)]()
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)]()

🚀 **[Live Dashboard → ](https://adelaide-metro-162176027068.asia-east2.run.app/)**

---

## Problem Statement

Adelaide Metro publishes GTFS static and GTFS-Realtime feeds, but raw feed data alone doesn't answer the operational questions that matter to planners and commuters. This project turns that raw feed into three concrete analytical answers, each corresponding to a dashboard tab:

### 1. Network Analytics — Is the network structured efficiently?
Static GTFS gives stops and routes, but not *how direct* those routes actually are relative to demand. **Circuity factor** (actual path length vs. geodesic span to the farthest stop) surfaces routes that loop excessively — a proxy for route design efficiency.

### 2. CBD Corridor Speed — Where does traffic actually bottleneck?
Combining scheduled trip times with stop-to-stop geospatial distance reveals realized speed per CBD corridor segment, exposing where the network underperforms relative to its designed schedule.

### 3. Delay Propagation Monitoring — Do delays cascade, and where do they start?
GTFS-Realtime `trip_updates` vs. scheduled `stop_times.txt` isolates root-cause stops where delay originates, then tracks how that delay compounds across downstream stops on the same trip.

---

## Overview

Adelaide Transit Pulse is an end-to-end data pipeline that ingests GTFS static and GTFS-Realtime feeds from Adelaide Metro, transforms them through a layered SQL model in BigQuery, and surfaces insights via an interactive Streamlit dashboard — including a 3D pydeck map for route/stop geometry that standard chart libraries can't render.

The pipeline runs on Bruin, pulling GTFS static (updated periodically) and GTFS-RT `trip_updates` (polled at short intervals), loading into BigQuery raw → staging → marts layers, and visualising across a two-view dashboard: schedule (batch) analysis and real-time delay monitoring.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Data Sources](#data-sources)
- [Data Pipeline](#data-pipeline)
- [Insights & Visualizations](#insights--visualizations)
- [Steps to Reproduce](#steps-to-reproduce)
- [About](#about)

---

## Tech Stack

<p align="center">
  <img width="100%" src="/docs/images/techstack.svg" alt="Techstack diagram">
</p>

| Layer          | Tool                  | Purpose                                      |
|----------------|-----------------------|-----------------------------------------------|
| Orchestration | Bruin | Pipeline orchestration + SQL transformations |
| Infrastructure | Terraform | Provision GCS, BigQuery, service accounts |
| Data Lake | Google Cloud Storage | Raw bucket for static GTFS |
| Data Warehouse | BigQuery | raw → staging → marts layers |
| Streaming |  Apache Kafka | Real-time trip update events via Aiven |
| Visualization | Streamlit + pydeck | Interactive dashboard (4 tabs) |
| Containerization | Docker | Container images for dashboard, batch, and streaming |
| Deployment | Google Cloud Run | Dashboard (Service) + Batch + Streaming (Jobs) |
| CI/CD | GitHub Actions + WIF | Auto-deploy on push to main |
| Scheduling | Cloud Scheduler | Trigger streaming jobs (1 min) + batch job (daily) |
| Cloud | GCP Free Tier | Compute, storage, and warehouse |
| Language | Python 3.11 | Ingestion scripts and dashboard |

### Why These Technologies?

**BigQuery** — Chosen for serverless geospatial functions (`ST_MakeLine`, `ST_Length`, `ST_Distance`) needed for circuity and corridor-speed calculations, without managing infrastructure.

**Bruin** — Unifies YAML-defined job orchestration and SQL assets under one CLI (`bruin run`), making raw → staging → marts dependency resolution explicit and reproducible.

**Apache Kafka (Hosted on Aiven)** - An open-source distributed event streaming platform used to bridge the gap between the Adelaide Metro GTFS Realtime API (polled every minute) and BigQuery. The producer worker pool publishes real-time transit updates to the adelaide-transit-rt topic, while the continuous consumer worker pool drains these events into BigQuery for real-time analysis.

| Overview | Topics |
|---|---|
| ![Overview](docs/images/aiven.png) | ![Topics](docs/images/topics.png) |
| Aiven Kafka cluster metrics for Adelaide Metro — showing topic/storage usage, producer rate, and consumer throughput | Three topics in use: `gtfs.vehicle_positions` for real-time vehicle positions, `gtfs.trip_updates` for real-time trip updates, and `gtfs.service_alerts` for service alerts |

**Streamlit** — Chosen for rapid dashboard development in pure Python, with `pydeck` support for 3D geospatial rendering (route shapes, stop density) that standard BI tools don't handle well.
| Tabs | Captures | Description 
|---|---|---|
| Network Analytics | ![Network Analytics](docs/images/streamlit_network_analytics.png) ![Network Analytics](docs/images/streamlit_spatial_reach.png) ![Network Analytics](docs/images/streamlit_spatial_reach-2.png) | Stop location maps, busiest routes, coverage hubs filtered by Local Government Areas (LGAs) | 
| Circuity Analysis | ![Circuity Analysis](docs/images/streamlit_circuity.png) | Operational dashboard tracking transit route circuity factors and spatial efficiency across network shapes. |
| CBD speed analysis | ![CBD speed analysis](docs/images/streamlit_CBD_speed.png) | Analyze vehicle speeds and traffic volumes across major Adelaide CBD corridors by time buckets.|
| Delay & Propagation Analytics | ![Delay & Propagation Analytics](docs/images/streamlit_dealy_propagation.png) | Real-time event volume, tracking how delays start at one stop and build up across the route. |

---

## Architecture
```mermaid
flowchart TD
    GH["🔧 GitHub Actions\npush to main"]
    GH -->|deploy.yml| CR_DASH["☁️ Cloud Run Service\nadelaide-metro\nStreamlit Dashboard"]
    GH -->|batch.yml| CR_BATCH["☁️ Cloud Run Job\nbatch-job\nBruin Pipeline"]

    CS1["⏰ Cloud Scheduler\nevery 1 min"]
    CS1 --> CR_PROD["☁️ Cloud Run Job\nproducer-job\n(Poll RT API every 1m)"]

    A["🌐 Adelaide Metro GTFS Static\ndata.gov.au"]
    B["🗺️ GEO LGA Data\ndata.gov.au / ABS"]
    RT_API["📡 Adelaide Metro GTFS Realtime\ndata.sa.gov.au"]

    CR_BATCH --> A
    CR_BATCH --> B
    A --> C["⚙️ Bruin Ingestion\ningest_gtfs_static.py"]
    B --> D["⚙️ Python Ingestion & Preprocess\ningest_geo_lga.py"]

    C --> E["🪣 Google Cloud Storage\ngtfs_static/adelaide-metro/"]
    D --> F["🪣 Google Cloud Storage\ngeo_lga/"]

    E -->|BQ Load Job| G["🗄️ BigQuery — raw\ngtfs_routes · gtfs_stops · gtfs_trips\ngtfs_stop_times · gtfs_shapes · gtfs_calendar"]
    F -->|BQ Load Job| I_LGA["🔧 BigQuery — staging\nstg_lgas"]

    CR_PROD --> RT_API
    RT_API -->|events| RP["📨 Apache Kafka\ngtfs_trip_updates topic"]

    CR_CONS["☁️ Cloud Run Service\nconsumer-worker-pool\n(Continuous Listener)"]
    RP --> CR_CONS
    CR_CONS -->|streaming insert| BQ_STREAM["🗄️ BigQuery — raw\ngtfs_realtime_trip_updates"]

    G --> I["🔧 Bruin Staging Assets\nstg_stops · stg_routes · stg_trips\nstg_stop_times · stg_shapes · stg_calendar"]
    BQ_STREAM --> I_RT["🔧 Bruin Staging Assets\nstg_rt_trip_updates"]

    I --> J["📊 Bruin Mart Assets\nmart_cbd_corridor_speed · mart_longest_routes\nmart_peak_hour_analysis · mart_ranked_stops\nmart_route_circuity · mart_transfer_hubs\nmart_route_segment_speeds · mart_shape_geometries\nmart_trips_per_route · mart_trips_per_stop"]
    I_LGA --> J
    I_RT --> J_RT["📊 Bruin Mart Assets\nmart_rt_delay_propagation"]

    J --> CR_DASH
    J_RT --> CR_DASH

    style GH fill:#2088FF,color:#fff,stroke:#2088FF
    style CR_DASH fill:#4285F4,color:#fff,stroke:#4285F4
    style CR_BATCH fill:#4285F4,color:#fff,stroke:#4285F4
    style CR_PROD fill:#4285F4,color:#fff,stroke:#4285F4
    style CR_CONS fill:#4285F4,color:#fff,stroke:#4285F4
    style CS1 fill:#34A853,color:#fff,stroke:#34A853
    style RP fill:#E52B50,color:#fff,stroke:#E52B50
    style A fill:#e8f4f8,stroke:#4285F4
    style B fill:#e8f4f8,stroke:#4285F4
    style RT_API fill:#e8f4f8,stroke:#4285F4
    style C fill:#fff3e0,stroke:#F97316
    style D fill:#fff3e0,stroke:#F97316
    style E fill:#e3f2fd,stroke:#4285F4
    style F fill:#e3f2fd,stroke:#4285F4
    style G fill:#e8eaf6,stroke:#4285F4
    style I fill:#fff3e0,stroke:#F97316
    style I_LGA fill:#fff3e0,stroke:#F97316
    style I_RT fill:#fff3e0,stroke:#F97316
    style J fill:#fff3e0,stroke:#F97316
    style J_RT fill:#fff3e0,stroke:#F97316
    style BQ_STREAM fill:#e8eaf6,stroke:#4285F4

```
---

## Project Structure
```
adelaide-metro/
├── Dockerfile                          # Dashboard container image
├── .dockerignore
├── requirements.txt                    # Python dependencies
├── .github/
│   └── workflows/
│       ├── deploy.yml                  # CI/CD: build + deploy dashboard on push to main
│       └── batch.yml                   # CI/CD: build + run batch job (daily at 06:00 HKT)
├── bruin/                              # Batch pipeline (Bruin)
│   ├── Dockerfile                      # Batch container image
│   ├── .bruin.yml                      # Bruin GCP connection config (gitignored)
│   ├── .bruin.yml.example
│   ├── pipeline.yml                    # Pipeline definition + daily schedule
│   └── assets/
│       ├── ingestion/
│       │   ├── ingest_gtfs_static.py   # Download GTFS Protobuf -> GCS -> BigQuery
│       ├── staging/
│       │   ├── stg_stops.sql
│       │   ├── stg_routes.sql
│       │   ├── stg_trips.sql
│       │   ├── stg_stop_times.sql
│       │   ├── stg_rt_service_alerts.sql
│       │   ├── stg_rt_trip_updates.sql
│       │   ├── stg_rt_vehicle_positions.sql
│       │   └── stg_calendar.sql
│       └── marts/
│           ├── mart_cbd_corridor_speed.sql
│           ├── mart_longest_routes.sql
│           ├── mart_peak_hour_analysis.sql
│           ├── mart_ranked_stops.sql
│           ├── mart_route_circuity.sql
│           ├── mart_transfer_hubs.sql
│           ├── mart_route_segment_speeds.sql
│           ├── mart_rt_delay_propagation.sql
│           ├── mart_shape_geometries.sql
│           ├── mart_trips_per_route.sql
│           └── mart_trips_per_stop.sql
├── dashboard/
│   └── App.py                          # Streamlit dashboard (3 tabs)
├── streaming/
│   ├── producer.py                     # One-shot: poll GTFS-RT API -> Kafka
│   └── consumer.py                     # One-shot: Kafka -> BigQuery
└── terraform/
    ├── main.tf                         # GCS + BigQuery + service account + IAM
    ├── variables.tf
    ├── outputs.tf
    └── terraform.tfvars.example
```

## Data Sources

### Adelaide Metro GTFS Static
| File | Contents |
|---|---|
| `shapes.txt` | Route shape geometry (used for circuity) |
| `stops.txt` | Stop locations |
| `stop_times.txt` | Scheduled arrival/departure per stop |
| `routes.txt`, `trips.txt` | Route/trip metadata |

### Adelaide Metro GTFS-Realtime
| Feed | Contents |
|---|---|
| `trip_updates` | Actual/predicted arrival-departure times per stop |

---

## Data Pipeline

### 1. Staging
Cleans and types raw GTFS files; groups shapes by `(shape_id, feed_version_id)` to handle schema evolution across feed updates.

### 2. Marts
- `mart_route_circuity` — actual path length vs. geodesic span
- `mart_cbd_corridor_speed` — realized speed per CBD segment vs. scheduled
- `mart_delay_propagation` — delay at origin stop vs. downstream stops (window functions on `stop_sequence`)

### 3. Dashboard
Streamlit app queries marts directly via the BigQuery Python client, rendering 3 tabs (Network Analytics, CBD Corridor Speed, Delay Propagation Monitoring) plus a 3D pydeck map for route geometry.

---

## Insights & Visualizations

**Network Analytics** — Circuity factor by route, ranked; geodesic span methodology explained; 3D pydeck map of route shapes and stop density.

**CBD Corridor Speed** — Scheduled vs. realized speed per corridor segment, volume overlay.

**Delay Propagation Monitoring** — Root-cause stop identification, delay cascade across downstream stops on the same trip.

---
