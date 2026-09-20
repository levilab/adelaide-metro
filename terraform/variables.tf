variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "gcs_location" {
  description = "GCS bucket region"
  type        = string
  default     = "ASIA-EAST2"
}

variable "bq_location" {
  description = "BigQuery dataset location (US for free tier)"
  type        = string
  default     = "US"
}

variable "cloud_run_region" {
  description = "Region for the realtime Cloud Run Job and Cloud Scheduler"
  type        = string
  default     = "asia-east2"
}

variable "rt_job_name" {
  description = "Name of the realtime transform Cloud Run Job deployed by CI"
  type        = string
  default     = "rt-transform-job"
}

variable "rt_scheduler_name" {
  description = "Name of the Cloud Scheduler job that invokes the realtime transform"
  type        = string
  default     = "rt-transform-every-5m"
}

variable "rt_transform_schedule" {
  description = "Cron schedule for realtime mart refreshes"
  type        = string
  default     = "*/5 * * * *"
}

variable "rt_transform_time_zone" {
  description = "Time zone used to evaluate the realtime refresh schedule"
  type        = string
  default     = "Australia/Adelaide"
}
