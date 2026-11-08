# ArgoCD (running in kind, step 13) deploys the chart on Floci's EKS, like it does on kind.
# Terraform only does what ArgoCD can't get from Git:
#   on Floci's EKS: the namespace, the database and OpenRouter Secrets, and a login for ArgoCD
#   on kind:        the ArgoCD cluster secret that registers Floci's EKS
# The app itself is 13-ArgoCD/apps/devops-ai-floci.yaml.

data "aws_secretsmanager_secret_version" "db" {
  secret_id = local.infra.db_secret_arn
}

locals {
  db           = jsondecode(data.aws_secretsmanager_secret_version.db.secret_string)
  database_url = "postgresql://${local.db.username}:${local.db.password}@${local.db.host}:${local.db.port}/${local.db.dbname}"
}

# ArgoCD runs in kind's container, Floci's EKS in its own: put kind on the floci network so they meet.
# It fails when already connected, which is fine.
resource "terraform_data" "kind_on_floci_network" {
  input = var.kind_node_container
  provisioner "local-exec" {
    command    = "docker network connect floci ${var.kind_node_container}"
    on_failure = continue
  }
}

# --- On Floci's EKS ---

resource "kubernetes_namespace_v1" "app" {
  metadata {
    name = "devops-ai"
  }
}

# The names values-argocd(-floci).yaml point at
resource "kubernetes_secret_v1" "database" {
  metadata {
    name      = "devops-ai-db-url"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  data = { DATABASE_URL = local.database_url }
}

resource "kubernetes_secret_v1" "openrouter" {
  metadata {
    name      = "openrouter"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }
  data = { OPENROUTER_API_KEY = var.openrouter_api_key }
}

# ArgoCD's login, as `argocd cluster add` would make it. A ServiceAccount token doesn't expire,
# unlike the 15-minute EKS tokens.
resource "kubernetes_service_account_v1" "argocd" {
  metadata {
    name      = "argocd-manager"
    namespace = "kube-system"
  }
}

resource "kubernetes_cluster_role_binding_v1" "argocd" {
  metadata {
    name = "argocd-manager"
  }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = "cluster-admin"
  }
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.argocd.metadata[0].name
    namespace = "kube-system"
  }
}

resource "kubernetes_secret_v1" "argocd_token" {
  metadata {
    name        = "argocd-manager-token"
    namespace   = "kube-system"
    annotations = { "kubernetes.io/service-account.name" = kubernetes_service_account_v1.argocd.metadata[0].name }
  }
  type                           = "kubernetes.io/service-account-token"
  wait_for_service_account_token = true
}

# --- On kind: register Floci's EKS in ArgoCD ---

resource "kubernetes_secret_v1" "argocd_cluster" {
  provider = kubernetes.kind

  metadata {
    name      = "cluster-floci-eks"
    namespace = "argocd"
    labels    = { "argocd.argoproj.io/secret-type" = "cluster" }
  }
  data = {
    name   = "floci-eks" # the destination name in 13-ArgoCD/apps/devops-ai-floci.yaml
    server = var.floci_eks_api
    config = jsonencode({
      bearerToken = kubernetes_secret_v1.argocd_token.data["token"]
      tlsClientConfig = {
        caData = data.aws_eks_cluster.main.certificate_authority[0].data # base64, as ArgoCD wants it
      }
    })
  }

  depends_on = [terraform_data.kind_on_floci_network]
}
