output "vm_public_ip" {
  value = google_compute_instance.gallery_vm.network_interface[0].access_config[0].nat_ip
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.mysql.connection_name
}

output "app_url" {
  value = "http://${google_compute_instance.gallery_vm.network_interface[0].access_config[0].nat_ip}:5001"
}