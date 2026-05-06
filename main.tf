resource "google_compute_network" "vpc" {
  name                    = "gallery-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "gallery-subnet"
  ip_cidr_range = "10.0.0.0/16"
  region        = var.region
  network       = google_compute_network.vpc.id
}

resource "google_compute_firewall" "allow_http" {
  name    = "allow-http"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
}
# HTTPS firewall (you only have HTTP/HTTPS combined but missing SSH for deployment)
resource "google_compute_firewall" "allow_ssh" {
  name    = "allow-ssh"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

resource "google_compute_firewall" "allow_app" {
  name    = "allow-app"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["5001"]
  }

  source_ranges = ["0.0.0.0/0"]
}

# Service Account
resource "google_service_account" "gallery_sa" {
  account_id   = "gallery-sa"
  display_name = "Gallery Service Account"
}

resource "google_project_iam_member" "sa_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.gallery_sa.email}"
}

resource "google_project_iam_member" "sa_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.gallery_sa.email}"
}

# Cloud SQL
resource "google_sql_database_instance" "mysql" {
  name             = "gallery-db"
  database_version = "MYSQL_8_0"
  region           = var.region

  depends_on = [google_service_networking_connection.private_vpc]

  settings {
    tier = "db-n1-standard-1"

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
  }

  deletion_protection = false
}

resource "google_sql_database" "gallery" {
  name     = var.db_name
  instance = google_sql_database_instance.mysql.name
}

resource "google_sql_user" "gallery_user" {
  name     = var.db_user
  instance = google_sql_database_instance.mysql.name
  password = var.db_password
}

# Private networking for Cloud SQL requires VPC peering
resource "google_compute_global_address" "private_ip" {
  name          = "private-ip-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# Compute Engine VM
resource "google_compute_instance" "gallery_vm" {
  name         = "gallery-vm"
  machine_type = "e2-standard-2"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id
    access_config {} # gives it a public IP
  }

  service_account {
    email  = google_service_account.gallery_sa.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = templatefile("${path.module}/startup.sh", {
    db_user        = var.db_user
    db_password    = var.db_password
    db_name        = var.db_name
    bucket_name    = var.bucket_name
    cloud_sql_conn = google_sql_database_instance.mysql.connection_name
  })

  tags = ["http-server", "https-server"]

  depends_on = [google_service_networking_connection.private_vpc]
}