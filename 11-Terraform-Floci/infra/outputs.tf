# The app stage (../app) reads these from this stage's state file.

output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_ids" {
  value = aws_subnet.private[*].id
}

output "runbooks_bucket" {
  value = aws_s3_bucket.runbooks.bucket
}

output "ecr_repository_url" {
  description = "Tag and push the chatbot image here"
  value       = aws_ecr_repository.app.repository_url
}

output "rds_endpoint" {
  description = "From your machine: psql -h localhost -p <port> -U devops knowledge"
  value       = "${aws_db_instance.main.address}:${aws_db_instance.main.port}"
}

output "db_secret_arn" {
  value = aws_secretsmanager_secret.db.arn
}

output "cluster_name" {
  value = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "kubeconfig_path" {
  value = abspath(local_sensitive_file.kubeconfig.filename)
}

output "deployer_access_key_id" {
  value = aws_iam_access_key.deployer.id
}

output "deployer_secret_access_key" {
  value     = aws_iam_access_key.deployer.secret
  sensitive = true
}

output "push_image" {
  description = "Build the step 09 image and push it to ECR (run from the repo root)"
  value       = <<-EOT
    docker build -f 09-Monitoring/Dockerfile -t ${aws_ecr_repository.app.repository_url}:09 .
    docker push ${aws_ecr_repository.app.repository_url}:09
  EOT
}
