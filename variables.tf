variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "db_password" {
  type        = string
  sensitive   = true
}
variable "db_user" {
  type    = string
  default = "gallery"
}

variable "db_name" {
  type    = string
  default = "gallerydb"
}

variable "bucket_name" {
  type = string
}