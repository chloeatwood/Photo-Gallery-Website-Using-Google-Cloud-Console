'''
MIT License

Copyright (c) 2019 Arshdeep Bahga and Vijay Madisetti

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

#!flask/bin/python
from flask import Flask, jsonify, abort, request, make_response, url_for
from flask import render_template, redirect, session
import os
#import boto3    
import time
#from boto3.dynamodb.conditions import Key, Attr
import exifread
import json
from flask import send_file
import io
from uuid import uuid4
import datetime

#To load values from .env file
from dotenv import load_dotenv
load_dotenv()

#For GCP
from google.cloud import storage
import mysql.connector

app = Flask(__name__, static_url_path="")


app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me")

UPLOAD_FOLDER = '/tmp/media'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])

# Google Cloud Storage
BUCKET_NAME = os.getenv("GCS_BUCKET")
if not BUCKET_NAME:
    raise RuntimeError("Missing env var GCS_BUCKET")

# Cloud SQL
#DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
#GOOGLE_APPLICATION_CREDENTIALS=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")


USERS_TABLE = "users"
PHOTOS_TABLE = "photos"

if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise RuntimeError("Missing one or more DB environment variables")

def get_db_connection():
    return mysql.connector.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        unix_socket="se-4220-final-project:us-central1:gallery-db|g"
    )

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': 'Bad request'}), 400)

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

def getExifData(path_name):
    f = open(path_name, 'rb')
    tags = exifread.process_file(f)
    ExifData={}
    for tag in tags.keys():
        if tag not in ('JPEGThumbnail', 
                        'TIFFThumbnail', 
                        'Filename', 
                        'EXIF MakerNote'):            
            key="%s"%(tag)
            val="%s"%(tags[tag])
            ExifData[key]=val
    return ExifData

def s3uploading(filename, file_stream):
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob("photos/" + filename)
    blob.upload_from_file(file_stream)
    return f"https://storage.googleapis.com/{BUCKET_NAME}/photos/{filename}"

def login_required(f):
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # TEMP BYPASS (remove later)
        if username == "team" and password == "1":
            session["logged_in"] = True
            session["username"] = "team"
            session["user_id"] = "test-user"
            return redirect("/")

        if not username or not password:
            return render_template("login.html", error="Please enter both fields")

        # Updated for GCP
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE username = %s AND password = %s",
            (username, password)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            return render_template("login.html", error="Invalid username or password")
        
        session["logged_in"] = True
        session["username"] = user["username"]
        session["user_id"] = user.get("userID")

        return redirect("/")

    return render_template("login.html")

#Registration route (WV)
@app.route('/register', methods =["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                (username, password)
            )
            conn.commit()
        except mysql.connector.errors.IntegrityError:
            cursor.close()
            conn.close()
            return render_template("register.html", error="Username already taken")
        cursor.close()
        conn.close()
        return redirect("/login")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/login")

@app.route('/', methods=['GET', 'POST'])
@login_required
def home_page():
    # Updated for GCP
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM photos WHERE userID = %s ORDER BY CreationTime DESC",
        (session["user_id"],)
    )
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('index.html', photos=items)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_photo():
    if request.method == 'POST':    
        uploadedFileURL=''

        file = request.files['imagefile']
        title = request.form['title']
        tags = request.form['tags']
        description = request.form['description']

        print(title,tags,description)
        if file and allowed_file(file.filename):
            filename = file.filename
            file_stream = file.stream
            uploadedFileURL = s3uploading(filename, file_stream)
            ExifData = {}  # Skip EXIF on App Engine (no local file)
            ts = time.time()
            timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            photo_id = str(uuid4())

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO photos 
                (userID, CreationTime, Title, Description, Tags, URL, ExifData)
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (session["user_id"], timestamp, title, description, tags,
                uploadedFileURL, json.dumps(ExifData))
            )
            conn.commit()
            cursor.close()
            conn.close()
        return redirect('/')
    else:
        return render_template('form.html')

@app.route('/photo/<photoID>', methods=['GET'])
@login_required
def view_photo(photoID):
    # Updated for GCP
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM photos WHERE PhotoID = %s AND userID = %s",
        (photoID, session["user_id"])
    )
    items = cursor.fetchall()
    cursor.close()
    conn.close()
 
    if not items:
        abort(404)
 
    tags = items[0]['Tags'].split(',')
    exifdata = json.loads(items[0]['ExifData']) if items[0]['ExifData'] else {}
 
    return render_template('photodetail.html', 
            photo=items[0], tags=tags, exifdata=exifdata)

@app.route('/search', methods=['GET'])
@login_required
def search_page():
    query = request.args.get('query', '')    
    # Updated for GCP
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT * FROM photos 
           WHERE userID = %s 
           AND (Title LIKE %s OR Description LIKE %s OR Tags LIKE %s)""",
        (session["user_id"], f"%{query}%", f"%{query}%", f"%{query}%")
    )
    items = cursor.fetchall()
    cursor.close()
    conn.close()
 
    return render_template('search.html', photos=items, searchquery=query)

@app.route('/download/<photoID>')
@login_required
def download_photo(photoID):

    # Updated for GCP
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM photos WHERE PhotoID = %s AND userID = %s",
        (photoID, session["user_id"])
    )
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    if not items:
        abort(404)

    photo = items[0]
    url = photo['URL']

    return redirect(url)


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5001)