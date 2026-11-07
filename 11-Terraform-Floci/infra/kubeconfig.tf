# A kubeconfig for the cluster, like `aws eks update-kubeconfig` writes: kubectl asks
# `aws eks get-token` (AWS CLI v2) for a 15-minute token, signed with the deployer's key.
# It holds that key, so it's git-ignored and written only readable by you.
resource "local_sensitive_file" "kubeconfig" {
  filename        = "${path.module}/kubeconfig"
  file_permission = "0600"
  content         = yamlencode({
    apiVersion        = "v1"
    kind              = "Config"
    "current-context" = var.name
    clusters          = [{
      name    = var.name
      cluster = {
        server                       = aws_eks_cluster.main.endpoint
        "certificate-authority-data" = aws_eks_cluster.main.certificate_authority[0].data
      }
    }]
    contexts = [{
      name    = var.name
      context = { cluster = var.name, user = "${var.name}-deployer" }
    }]
    users = [{
      name = "${var.name}-deployer"
      user = {
        exec = {
          apiVersion = "client.authentication.k8s.io/v1beta1"
          command    = "aws"
          args       = ["eks", "get-token", "--cluster-name", aws_eks_cluster.main.name, "--region", var.region, "--output", "json"]
          env        = [
            { name = "AWS_ACCESS_KEY_ID", value = aws_iam_access_key.deployer.id },
            { name = "AWS_SECRET_ACCESS_KEY", value = aws_iam_access_key.deployer.secret },
          ]
          interactiveMode = "Never"
        }
      }
    }]
  })
}
