# This stage deploys the chatbot onto the cluster the infra stage created. It's a separate stage
# because the Kubernetes provider needs the cluster to exist before Terraform can plan against it.

data "terraform_remote_state" "infra" {
  backend = "local"
  config = {
    path = "${path.module}/../infra/terraform.tfstate"
  }
}

locals {
  infra = data.terraform_remote_state.infra.outputs
}

# As the deployer: Floci signs EKS logins only for a real IAM key, not its public test/test
provider "aws" {
  region     = var.region
  access_key = local.infra.deployer_access_key_id
  secret_key = local.infra.deployer_secret_access_key

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    eks            = var.floci_endpoint
    secretsmanager = var.floci_endpoint
    sts            = var.floci_endpoint
  }
}

data "aws_eks_cluster" "main" {
  name = local.infra.cluster_name
}

# A 15-minute token, the same one `aws eks get-token` makes. Enough for one apply.
data "aws_eks_cluster_auth" "main" {
  name = local.infra.cluster_name
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.main.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.main.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.main.token
}
