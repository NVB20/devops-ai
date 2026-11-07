# The standard AWS provider, pointed at Floci instead of AWS. test/test is Floci's public local key:
# fine for creating resources, but Floci refuses it for EKS logins, so iam.tf creates a deployer user.
provider "aws" {
  region     = var.region
  access_key = "test"
  secret_key = "test"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  # Every service this configuration uses must point at Floci, or the provider calls real AWS
  endpoints {
    ec2            = var.floci_endpoint
    ecr            = var.floci_endpoint
    eks            = var.floci_endpoint
    iam            = var.floci_endpoint
    rds            = var.floci_endpoint
    s3             = var.floci_endpoint
    secretsmanager = var.floci_endpoint
    sts            = var.floci_endpoint
  }

  default_tags {
    tags = {
      Project   = "devops-ai"
      Step      = "11"
      ManagedBy = "terraform"
    }
  }
}
