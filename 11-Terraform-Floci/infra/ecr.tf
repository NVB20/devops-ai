# Where the chatbot image goes. With Floci's path URI style the URL is
# localhost:4566/000000000000/us-east-1/devops-ai-app, and the EKS cluster pulls from it as-is.
resource "aws_ecr_repository" "app" {
  name                 = "${var.name}-app"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true # recorded; Floci doesn't scan
  }
}
