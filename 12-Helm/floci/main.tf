data "aws_secretsmanager_secret_version" "db" {
  secret_id = local.infra.db_secret_arn
}

locals {
  db           = jsondecode(data.aws_secretsmanager_secret_version.db.secret_string)
  database_url = "postgresql://${local.db.username}:${local.db.password}@${local.db.host}:${local.db.port}/${local.db.dbname}"
}

resource "helm_release" "devops_ai" {
  name             = "devops-ai"
  chart            = "${path.module}/../devops-ai"
  namespace        = "devops-ai"
  create_namespace = true

  values = [file("${path.module}/../values-floci.yaml")]

  set = [
    { name = "image.repository", value = local.infra.ecr_repository_url },
    { name = "image.tag", value = var.image_tag, type = "string" },
    { name = "llm.provider", value = var.llm_provider },
  ]

  set_sensitive = [
    { name = "database.url", value = local.database_url },
    { name = "llm.openrouterApiKey", value = var.openrouter_api_key, type = "string" },
  ]

  # Like `helm upgrade --wait --wait-for-jobs`: done only when the ingest Job has finished and the app is ready
  wait          = true
  wait_for_jobs = true
  timeout       = 900 # the first pull of the image from ECR takes a while
}
