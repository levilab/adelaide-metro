# Setup & Deployment

[← Back to README](../README.md) · [Data model](data-model.md)

This guide covers a first-time local setup backed by GCP, cloud deployment, scheduling, and validation. For an existing warehouse, the README's quick start is enough to launch the dashboard.

---

## Local Setup

The commands below use Bash from Linux, macOS, or WSL on Windows. Local Kafka runs through Docker; warehouse storage and queries still require GCP.

### 1. Prerequisites and project configuration

- Python 3.11, Bruin CLI, Terraform 1.6+, and gcloud CLI.
- Docker with Compose for local Kafka.
- A GCP project with billing and the APIs needed for BigQuery and Cloud Storage. Cloud deployment additionally needs Cloud Run, Artifact Registry, and Cloud Scheduler.
- Credentials with permission to provision infrastructure, load data, and run BigQuery queries.

**Project portability:** SQL assets contain fully qualified references to `adelaide-metro-505702`. Before using your own project, update these references in `bruin/assets/`, the generated connection in `bruin/Dockerfile`, and project/bucket/image settings in the deployment workflows. Setting `GOOGLE_CLOUD_PROJECT` alone does not redirect all SQL reads.

```bash
git clone https://github.com/levilab/adelaide-metro.git
cd adelaide-metro
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GCS_BUCKET="${GOOGLE_CLOUD_PROJECT}-raw"
```

Use Application Default Credentials locally; Cloud Run uses its assigned service account. If using a service-account credential file, set `GOOGLE_APPLICATION_CREDENTIALS` to that file's path.

### 2. Provision infrastructure

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Edit the copied file with actual values, for example:

```hcl
project_id   = "your-project-id"
gcs_location = "ASIA-EAST2"
bq_location  = "US"
```

```bash
terraform -chdir=terraform init
terraform -chdir=terraform plan
terraform -chdir=terraform apply
```

Terraform provisions the bucket, five datasets, service accounts/IAM, and the five-minute realtime scheduler. The scheduler targets `rt-transform-job`, which must be deployed separately before scheduled executions can succeed. Terraform does not provision Kafka, Workload Identity Federation, Artifact Registry repositories, or Cloud Run images and workloads.

### 3. Configure Bruin

From the repository root:

```bash
cp .bruin.yml.example .bruin.yml
```

Replace `<GCP_PROJECT_ID>` with your project ID and keep the connection location aligned with the BigQuery datasets. The template uses the `gcp` connection and Application Default Credentials. Keep this configuration at the repository root for the following commands.

### 4. Start realtime ingestion

```bash
docker compose up -d kafka
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export BQ_DATASET="streaming"
```

Ensure the broker has all four topics listed in [the realtime ingestion table](data-model.md#realtime-ingestion), either through topic creation or broker auto-creation. For local plaintext Kafka, leave `KAFKA_SASL_USERNAME` and `KAFKA_SASL_PASSWORD` unset.

Run these commands in two separate terminals, each with the virtual environment and environment variables configured:

```bash
python streaming/producer.py
```

```bash
python streaming/consumer.py
```

Wait until the consumer has created the four `streaming` tables and loaded successful polling status before running the full Bruin pipeline. Tables are created when a nonempty batch is loaded; an empty alerts feed may require separately creating the alerts table with the schema in `streaming/consumer.py`. Realtime checks require a recent successful trip-update poll. For hosted Kafka, the scripts use SASL credentials and a CA file at `/app/ca.pem`; the deployment image supplies that path.

### 5. Build the warehouse tables

From the repository root, while producer and consumer remain running:

```bash
bruin validate --fast bruin
bruin run bruin
```

The full run builds ingestion, staging, core, and marts, including realtime assets. After the initial build, refresh the delay path independently:

```bash
bruin run bruin/assets/staging/stg_rt_trip_updates.sql --downstream
```

This requires the scheduled core tables to exist. A standalone SQL asset run does not rebuild its upstream inputs.

### 6. Launch the dashboard

From the repository root:

```bash
streamlit run dashboard/App.py
```

The app requires `GOOGLE_CLOUD_PROJECT` and the dashboard mart tables listed in [the data model](data-model.md#dashboard-marts), including the peak-by-type input used to build network KPIs. The Compose file starts only Kafka; it does not launch the dashboard or Bruin pipeline.

---

## Deployment & Scheduling

| Component | Owner | Trigger / behavior |
| --- | --- | --- |
| Dashboard service `adelaide-metro` | `.github/workflows/deploy.yml` | Relevant pushes to `main` or manual dispatch |
| Producer `gtfs-kafka-producer` | Same workflow | Continuous Cloud Run Worker Pool; independent feed polling intervals |
| Consumer `gtfs-kafka-consumer` | Same workflow | Continuous Cloud Run Worker Pool; one worker per topic |
| `batch-job` | `.github/workflows/batch.yml` | Full pipeline on relevant pushes, manual dispatch, and daily at 12:00 UTC (21:30 ACST / 22:30 ACDT) |
| `rt-transform-job` | Same batch workflow | Deploys the Bruin image with a trip-update staging/downstream command |
| `rt-transform-every-5m` | Terraform | Invokes the realtime Job every five minutes, using `Australia/Adelaide` timezone |

GitHub Actions authenticates using `WIF_PROVIDER` and `WIF_SERVICE_ACCOUNT`. Dashboard/streaming deployment also requires `APP_CA_PEM`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SASL_USERNAME`, and `KAFKA_SASL_PASSWORD` secrets. Provision the WIF setup, Artifact Registry repository, and hosted Kafka topics separately, and update the workflow settings for your project before deployment.

The root Dockerfile requires `ca.pem` in the build context; `deploy.yml` creates it from `APP_CA_PEM`. The batch image generates its own Bruin connection. Scheduled batch runs reuse the deployed Job; pushes and manual runs build/deploy the image before executing it.

The current workflows assign `bruin-pipeline` to the dashboard and streaming workloads. Terraform also creates a `streamlit-dashboard` account, but the dashboard workflow does not currently use it.

---

## Validation

Run the existing producer/consumer unit tests without starting Kafka or connecting to GCP:

```bash
python -m unittest discover -s tests -v
```

Repository checks used by CI:

```bash
bruin validate --fast bruin
terraform -chdir=terraform fmt -check
terraform -chdir=terraform init -backend=false -input=false
terraform -chdir=terraform validate
```

The PR workflow runs these checks for changes to its configured pipeline, streaming, Terraform, test, dependency, and workflow paths. Fast Bruin validation checks pipeline definitions; runtime SQL and freshness checks still require warehouse data and a running realtime ingestion path.

---

## Deployment Notes

Continuously running Worker Pools, BigQuery operations, and the dashboard's minimum instance require a project-specific cost budget. This configuration does not guarantee free-tier operation.

Terraform does not cover the complete deployment setup. Provision WIF, hosted Kafka, the Artifact Registry repository, and required APIs separately. The dashboard currently uses `bruin-pipeline`; align it with the read-only `streamlit-dashboard` account if tightening runtime permissions.
