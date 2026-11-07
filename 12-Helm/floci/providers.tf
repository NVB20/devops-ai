# Step 11's app stage, the Helm way: instead of ~200 lines of Kubernetes resources it installs the
# chart in ../devops-ai. It reads the outputs of step 11's infra stage, which must be applied first.

data "terraform_remote_state" "infra" {
  backend = "local"
  config = {
    path = "${path.module}/../../11-Terraform-Floci/infra/terraform.tfstate"
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

data "aws_eks_cluster_auth" "main" {
  name = local.infra.cluster_name
}

provider "helm" {
  kubernetes = {
    host                   = data.aws_eks_cluster.main.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.main.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.main.token
  }
}
