# The chatbot on Floci's EKS, the same shape as step 10 on kind, except:
#   - the database is the RDS instance (no Postgres in the cluster)
#   - the image comes from ECR
#   - the database URL comes from Secrets Manager

data "aws_secretsmanager_secret_version" "db" {
  secret_id = local.infra.db_secret_arn
}

locals {
  db           = jsondecode(data.aws_secretsmanager_secret_version.db.secret_string)
  database_url = "postgresql://${local.db.username}:${local.db.password}@${local.db.host}:${local.db.port}/${local.db.dbname}"
  image        = "${local.infra.ecr_repository_url}:${var.image_tag}"
  labels       = { "app.kubernetes.io/part-of" = "devops-ai" }
}

resource "kubernetes_namespace_v1" "main" {
  metadata {
    name   = "devops-ai"
    labels = local.labels
  }
}

resource "kubernetes_secret_v1" "database" {
  metadata {
    name      = "database"
    namespace = kubernetes_namespace_v1.main.metadata[0].name
  }
  data = {
    DATABASE_URL = local.database_url
  }
}

resource "kubernetes_secret_v1" "openrouter" {
  count = var.openrouter_api_key != "" ? 1 : 0
  metadata {
    name      = "openrouter"
    namespace = kubernetes_namespace_v1.main.metadata[0].name
  }
  data = {
    OPENROUTER_API_KEY = var.openrouter_api_key
  }
}

resource "kubernetes_config_map_v1" "app" {
  metadata {
    name      = "devops-ai"
    namespace = kubernetes_namespace_v1.main.metadata[0].name
  }
  data = {
    LLM_PROVIDER     = var.llm_provider
    OPENROUTER_MODEL = var.openrouter_model
    OLLAMA_BASE_URL  = var.ollama_base_url
    OLLAMA_MODEL     = var.ollama_model
  }
}

# Loads the runbooks into RDS, and Terraform waits until it has. Delete it (terraform apply
# -replace=kubernetes_job_v1.ingest) to load them again after a change to knowledge-base/.
resource "kubernetes_job_v1" "ingest" {
  metadata {
    name      = "ingest"
    namespace = kubernetes_namespace_v1.main.metadata[0].name
    labels    = merge(local.labels, { "app.kubernetes.io/name" = "ingest" })
  }

  spec {
    backoff_limit = 6
    template {
      metadata {
        labels = merge(local.labels, { "app.kubernetes.io/name" = "ingest" })
      }
      spec {
        restart_policy = "OnFailure"
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
        }
        container {
          name    = "ingest"
          image   = local.image
          command = ["python", "-m", "app.ingest"]
          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.database.metadata[0].name
                key  = "DATABASE_URL"
              }
            }
          }
          resources {
            requests = { cpu = "200m", memory = "512Mi" }
            limits   = { memory = "1Gi" }
          }
        }
      }
    }
  }

  wait_for_completion = true
  timeouts {
    create = "15m" # the first pull of the image from ECR takes a while
  }
}

resource "kubernetes_deployment_v1" "app" {
  metadata {
    name      = "app"
    namespace = kubernetes_namespace_v1.main.metadata[0].name
    labels    = merge(local.labels, { "app.kubernetes.io/name" = "devops-ai-app" })
  }

  spec {
    replicas = 1
    selector {
      match_labels = { "app.kubernetes.io/name" = "devops-ai-app" }
    }

    template {
      metadata {
        labels = merge(local.labels, { "app.kubernetes.io/name" = "devops-ai-app" })
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = "8000"
          "prometheus.io/path"   = "/metrics"

          # A new model, key or database URL restarts the pods, so they pick it up (only hashes, no secrets)
          "devops-ai/config-hash" = sha256(jsonencode([kubernetes_config_map_v1.app.data, sha256(var.openrouter_api_key), sha256(local.database_url)]))
        }
      }

      spec {
        security_context {
          run_as_non_root = true
          run_as_user     = 1000
        }

        container {
          name  = "app"
          image = local.image

          port {
            name           = "http"
            container_port = 8000
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.app.metadata[0].name
            }
          }
          env_from {
            secret_ref {
              name     = "openrouter"
              optional = true # not needed with llm_provider = "ollama"
            }
          }
          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.database.metadata[0].name
                key  = "DATABASE_URL"
              }
            }
          }

          # Same probes as step 10: readiness follows the database, liveness only the port
          startup_probe {
            tcp_socket {
              port = "http"
            }
            period_seconds    = 5
            failure_threshold = 24
          }
          readiness_probe {
            http_get {
              path = "/health"
              port = "http"
            }
            period_seconds  = 10
            timeout_seconds = 6
          }
          liveness_probe {
            tcp_socket {
              port = "http"
            }
            period_seconds = 20
          }

          resources {
            requests = { cpu = "250m", memory = "768Mi" }
            limits   = { memory = "3Gi" }
          }
        }
      }
    }
  }

  # The runbooks must be in RDS first, or /health fails and the rollout never finishes
  depends_on = [kubernetes_job_v1.ingest, kubernetes_secret_v1.openrouter]

  timeouts {
    create = "10m"
    update = "10m"
  }
}

resource "kubernetes_service_v1" "app" {
  metadata {
    name      = "app"
    namespace = kubernetes_namespace_v1.main.metadata[0].name
    labels    = { "app.kubernetes.io/name" = "devops-ai-app" }
  }
  spec {
    selector = { "app.kubernetes.io/name" = "devops-ai-app" }
    port {
      name        = "http"
      port        = 8000
      target_port = "http"
    }
  }
}
