# The knowledge base: RDS Postgres 17. compose.yml makes Floci run it from the pgvector image,
# and the master user is a superuser there, so the ingest's CREATE EXTENSION vector works.
resource "random_password" "db" {
  length  = 24
  special = false # it goes into a postgresql:// URL
}

resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier        = var.name
  engine            = "postgres"
  engine_version    = "17"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = "knowledge"
  username = "devops"
  password = random_password.db.result
  # No port: Floci gives each database a port of its proxy range (7001-7099), read back into .port

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  skip_final_snapshot = true
  apply_immediately   = true
}
