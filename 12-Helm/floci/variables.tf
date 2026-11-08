variable "floci_endpoint" {
  type    = string
  default = "http://localhost:4566"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "openrouter_api_key" {
  description = "Pass it as TF_VAR_openrouter_api_key, never in a file in Git"
  type        = string
  default     = ""
  sensitive   = true
}

variable "floci_eks_api" {
  description = <<-EOT
    Floci's EKS API as ArgoCD (inside kind) reaches it: the EKS container's address on the floci network,
    which its certificate accepts. Find it with:
    docker inspect floci-aws-eks-devops-ai --format '{{(index .NetworkSettings.Networks "floci").IPAddress}}'
  EOT
  type        = string
  default     = "https://172.29.0.5:6443"
}

variable "kind_node_container" {
  description = "The kind node's container, joined to the floci network so ArgoCD can reach Floci's EKS"
  type        = string
  default     = "devops-ai-control-plane"
}

variable "kind_kubeconfig" {
  type    = string
  default = "~/.kube/config"
}

variable "kind_context" {
  type    = string
  default = "kind-devops-ai"
}
