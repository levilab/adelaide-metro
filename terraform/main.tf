terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.6.0"
}

provider "google" {
  project = var.project_id
  region  = var.gcs_location
}

resource "google_storage_bucket" "raw" {
  name          = "${var.project_id}-raw"
  location      = var.gcs_location
  force_destroy = false

  uniform_bucket_level_access = true
}

resource "google_bigquery_dataset" "raw" {
  dataset_id                 = "raw"
  location                   = var.bq_location
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "staging" {
  dataset_id                 = "staging"
  location                   = var.bq_location
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "core" {
  dataset_id                 = "core"
  location                   = var.bq_location
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "marts" {
  dataset_id                 = "marts"
  location                   = var.bq_location
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "streaming" {
  dataset_id                 = "streaming"
  location                   = var.bq_location
  delete_contents_on_destroy = true
}

# ── Bruin Service Account ───────────────────────────────────────

resource "google_service_account" "bruin" {
  account_id   = "bruin-pipeline"
  display_name = "Bruin Pipeline Service Account"
}

resource "google_project_iam_member" "bruin_bq" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.bruin.email}"
}

resource "google_project_iam_member" "bruin_bq_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.bruin.email}"
}

resource "google_project_iam_member" "bruin_gcs" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.bruin.email}"
}

resource "google_project_iam_member" "bruin_bq_read_session" {
  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.bruin.email}"
}

resource "google_project_iam_member" "bruin_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.bruin.email}"
}

resource "google_project_iam_member" "bruin_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.bruin.email}"
}

resource "google_project_iam_member" "bruin_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.bruin.email}"
}

resource "google_service_account_iam_member" "bruin_act_as" {
  service_account_id = google_service_account.bruin.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.bruin.email}"
}

# ── Realtime Transform Scheduler ───────────────────────────────

resource "google_project_service" "cloud_scheduler" {
  project            = var.project_id
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "rt_scheduler" {
  account_id   = "rt-transform-scheduler"
  display_name = "Realtime Transform Scheduler"
}

resource "google_project_iam_member" "rt_scheduler_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.rt_scheduler.email}"
}

resource "google_cloud_scheduler_job" "rt_transform" {
  name        = var.rt_scheduler_name
  description = "Refresh realtime staging, facts, and dashboard marts"
  region      = var.cloud_run_region
  schedule    = var.rt_transform_schedule
  time_zone   = var.rt_transform_time_zone

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.cloud_run_region}/jobs/${var.rt_job_name}:run"

    oauth_token {
      service_account_email = google_service_account.rt_scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  retry_config {
    retry_count          = 1
    min_backoff_duration = "30s"
    max_backoff_duration = "60s"
    max_doublings        = 1
  }

  depends_on = [
    google_project_service.cloud_scheduler,
    google_project_iam_member.rt_scheduler_run_invoker,
  ]
}

# ── Streamlit Dashboard Service Account ───────────────────────────────────────
resource "google_service_account" "streamlit" {
  account_id   = "streamlit-dashboard"
  display_name = "Streamlit Dashboard Service Account"
}

resource "google_project_iam_member" "streamlit_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.streamlit.email}"
}

resource "google_project_iam_member" "streamlit_bq_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.streamlit.email}"
}
