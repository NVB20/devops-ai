output "argocd_cluster" {
  description = "How ArgoCD knows Floci's EKS (the destination of 13-ArgoCD/apps/devops-ai-floci.yaml)"
  value       = "floci-eks at ${var.floci_eks_api}"
}

output "open_the_chat" {
  value = <<-EOT
    kubectl --kubeconfig ${local.infra.kubeconfig_path} -n devops-ai port-forward svc/devops-ai 8083:8000
    then open http://127.0.0.1:8083/ui
  EOT
}
