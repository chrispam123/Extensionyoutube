terraform {
  backend "s3" {
    bucket       = "extension-terraform-state-youtube"
    key          = "prod/terraform.tfstate" # <--- CLAVE: Carpeta 'prod'
    region       = "us-east-1"
    use_lockfile = true
  }
}
