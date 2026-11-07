output "release" {
  description = "See it with: helm --kubeconfig <kubeconfig_path of step 11> -n devops-ai history devops-ai"
  value       = "${helm_release.devops_ai.name} in namespace ${helm_release.devops_ai.namespace}"
}

output "open_the_chat" {
  value = <<-EOT
    kubectl --kubeconfig ${local.infra.kubeconfig_path} -n devops-ai port-forward svc/devops-ai 8083:8000
    then open http://127.0.0.1:8083/ui
  EOT
}
