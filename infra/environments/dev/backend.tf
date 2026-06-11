terraform {
  backend "s3" {
    bucket       = "extension-terraform-state-mzkchris"
    key          = "dev/terraform.tfstate" # <--- DIFERENTE AL DE LOCAL
    region       = "us-east-1"
    use_lockfile = true
  }
}
