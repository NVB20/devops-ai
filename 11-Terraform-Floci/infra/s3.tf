# The runbooks, versioned in S3: a copy of knowledge-base/ that the ingest could read instead of the image's
resource "aws_s3_bucket" "runbooks" {
  bucket        = "${var.name}-runbooks"
  force_destroy = true # terraform destroy empties it first
}

resource "aws_s3_bucket_versioning" "runbooks" {
  bucket = aws_s3_bucket.runbooks.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "runbooks" {
  bucket                  = aws_s3_bucket.runbooks.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "runbook" {
  for_each     = fileset("${path.module}/../../knowledge-base", "*.md")
  bucket       = aws_s3_bucket.runbooks.id
  key          = each.value
  source       = "${path.module}/../../knowledge-base/${each.value}"
  etag         = filemd5("${path.module}/../../knowledge-base/${each.value}") # re-uploads a runbook when it changes
  content_type = "text/markdown"
}
