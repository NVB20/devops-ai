variable "floci_endpoint" {
  type    = string
  default = "http://localhost:4566"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "image_tag" {
  description = "The tag pushed to ECR (see step 11's push_image output)"
  type        = string
  default     = "14"
}

variable "llm_provider" {
  description = "openrouter or ollama"
  type        = string
  default     = "openrouter"
}

variable "openrouter_api_key" {
  description = "Pass it as TF_VAR_openrouter_api_key, never in a file in Git"
  type        = string
  default     = ""
  sensitive   = true
}
