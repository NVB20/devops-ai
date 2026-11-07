variable "floci_endpoint" {
  description = "Where Floci listens (11-Terraform-Floci/compose.yml publishes it on 4566)"
  type        = string
  default     = "http://localhost:4566"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  description = "Prefix of every resource name"
  type        = string
  default     = "devops-ai"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "kubernetes_version" {
  description = "EKS version; Floci runs the matching k3s release (1.33 -> rancher/k3s:v1.33.1-k3s1)"
  type        = string
  default     = "1.33"
}

variable "db_host_in_cluster" {
  description = <<-EOT
    The database host the pods use. Floci's RDS proxy runs inside the Floci container, and Floci's DNS
    answers localhost.floci.io with that container's address inside the clusters it starts.
    On real AWS, set it to "" to use the RDS endpoint address.
  EOT
  type        = string
  default     = "localhost.floci.io"
}
