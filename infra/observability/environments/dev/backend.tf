terraform {
  backend "s3" {
    bucket       = "extension-terraform-state-youtube"
    key          = "observability/dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }
}
