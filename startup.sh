#!/bin/bash
apt-get update -y
apt-get install -y python3-pip python3-venv git wget

# Install Cloud SQL proxy
wget https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64 -O /usr/local/bin/cloud_sql_proxy
chmod +x /usr/local/bin/cloud_sql_proxy

# Clone your app (replace with your actual repo or upload method)
cd /opt
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git gallery
cd gallery

# Create .env file
cat > .env <<EOF
FLASK_SECRET_KEY=supersecretkey
GCS_BUCKET=${bucket_name}
DB_USER=${db_user}
DB_PASSWORD=${db_password}
DB_NAME=${db_name}
EOF

# Install Python deps
pip3 install -r requirements.txt

# Start Cloud SQL proxy
/usr/local/bin/cloud_sql_proxy -instances=${cloud_sql_conn}=unix:/cloudsql/${cloud_sql_conn} &

sleep 5

# Initialize DB schema
python3 -c "
import mysql.connector
conn = mysql.connector.connect(
    user='${db_user}', password='${db_password}',
    database='${db_name}',
    unix_socket='/cloudsql/${cloud_sql_conn}'
)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    userID INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
)''')
c.execute('''CREATE TABLE IF NOT EXISTS photos (
    PhotoID INT AUTO_INCREMENT PRIMARY KEY,
    userID VARCHAR(100),
    CreationTime DATETIME,
    Title VARCHAR(255),
    Description TEXT,
    Tags VARCHAR(255),
    URL TEXT,
    ExifData JSON
)''')
conn.commit()
conn.close()
"

# Run Flask app
nohup python3 app.py > /var/log/gallery.log 2>&1 &