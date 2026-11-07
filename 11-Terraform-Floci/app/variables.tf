variable "floci_endpoint" {
  type    = string
  default = "http://localhost:4566"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "image_tag" {
  description = "The tag pushed to ECR (see the infra stage's push_image output)"
  type        = string
  default     = "09"
}

variable "llm_provider" {
  description = "openrouter or ollama"
  type        = string
  default     = "openrouter"

  validation {
    condition     = contains(["openrouter", "ollama"], var.llm_provider)
    error_message = "llm_provider must be openrouter or ollama."
  }
}

variable "openrouter_api_key" {
  description = "Needed when llm_provider is openrouter. Pass it as TF_VAR_openrouter_api_key, never in a file in Git."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openrouter_model" {
  type    = string
  default = "openrouter/free"
}

variable "ollama_base_url" {
  type    = string
  default = "http://host.docker.internal:11434/v1"
}

variable "ollama_model" {
  type    = string
  default = "llama3.2"
}
