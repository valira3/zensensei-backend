variable "project_id" { type = string }
variable "environment" { type = string }
variable "cloud_run_services" {
  type    = list(string)
  default = []
}
variable "alert_email" {
  type    = string
  default = "ops@zensensei.io"
}
variable "error_rate_threshold" { type = number; default = 0.01 }
variable "latency_threshold_ms" { type = number; default = 500 }
variable "cpu_threshold" { type = number; default = 0.8 }
variable "memory_threshold" { type = number; default = 0.85 }
