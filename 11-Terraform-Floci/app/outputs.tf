output "image" {
  value = local.image
}

output "open_the_chat" {
  description = "The cluster's ports aren't published, so reach the app through kubectl (run from the repo root)"
  value       = <<-EOT
    kubectl --kubeconfig ${local.infra.kubeconfig_path} -n devops-ai port-forward svc/app 8083:8000
    then open http://127.0.0.1:8083/ui
  EOT
}
