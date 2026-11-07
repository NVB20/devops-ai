# The database credentials in Secrets Manager. The app stage reads them from here to build the
# Kubernetes Secret, so the password never goes through a tfvars file or the command line.
resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.name}/database"
  recovery_window_in_days = 0 # delete at once on destroy, so the name can be reused
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = aws_db_instance.main.username
    password = random_password.db.result
    dbname   = aws_db_instance.main.db_name
    host     = var.db_host_in_cluster != "" ? var.db_host_in_cluster : aws_db_instance.main.address
    port     = aws_db_instance.main.port
  })
}
