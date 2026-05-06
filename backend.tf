terraform {
  backend "gcs" {
    bucket = "chloe-gallery-terraform-state"
    prefix = "terraform/state"
  }
}