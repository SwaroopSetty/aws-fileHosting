import boto3
import os.path
import pytz, datetime
from tzlocal import get_localzone
from flask import Flask, request, render_template, send_from_directory, json, flash
from flask.ext.mysql import MySQL
from werkzeug import generate_password_hash, check_password_hash
from passlib.hash import sha256_crypt

mysql = MySQL()
app = Flask(__name__)

app.config['SECRET_KEY'] = 'super secret key'

# MySQL configurations
app.config['MYSQL_DATABASE_USER'] = 'root'
app.config['MYSQL_DATABASE_PASSWORD'] = ''
app.config['MYSQL_DATABASE_DB'] = 'Locations'
app.config['MYSQL_DATABASE_HOST'] = 'cloudcomputing.cljvknvits4o.us-west-2.rds.amazonaws.com'
mysql.init_app(app)
conn = mysql.connect()

# Connection to  Amazon S3
s3 = boto3.resource(service_name='s3', aws_access_key_id='',
aws_secret_access_key='',
region_name='us-west-2')

bucket = s3.Bucket('aws-login-cloud-computing')

bucketName = 'aws-login-cloud-computing'

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])

###########HOME PAGE##########
@app.route('/')
def hello_world():
    return render_template('login.html')

###########REGISTRATION PAGE##########
@app.route('/register', methods=['POST', 'GET'])
def register():
    _name = request.form['name_reg']
    _password = request.form['password_reg']
    if _name and _password :
        cursor = conn.cursor()
        _hashed_password = sha256_crypt.encrypt(_password)
        cursor.callproc('user_register',(_name,_hashed_password))
        data = cursor.fetchall()
        cursor.close() 
        if len(data) is 0:
            conn.commit()
            bucketName = _name+'cc2016'
            s3.create_bucket(Bucket=bucketName)
            flash('User Created Successfully')
            return render_template('login.html')
        else:
            return json.dumps({'error':str(data[0])})
    else:
        return json.dumps({'html':'<span>Enter the required fields</span>'})

    # return render_template('login.html')

############LOGIN AND BUCKET LIST LOGIC########
@app.route('/login', methods=['POST', 'GET'])
def login():
    # Check if user is a part of names.txt
    _name = request.form['name']
    _password = request.form['password']
    if _name and _password :
        cursor = conn.cursor()
        cursor.callproc('user_login',(_name,_password))
        data = cursor.fetchall()
        print data
        cursor.close() 
        if len(data) is 0 :
            return 'You do not have access, Register'
        else:
            for row in data :
                _nameDB = row[0]
                _hashedPassword = row[1]
                print _hashedPassword
            if sha256_crypt.verify(_password, _hashedPassword):
                # Get the file names from bucket
                L = []
                bucketName = request.form['name']+'cc2016'
                bucket = s3.Bucket(bucketName)
                for obj_all in bucket.objects.all():
                    obj = s3.Object(bucket_name=obj_all.bucket_name, key=obj_all.key)
                    #local = get_localzone()
                    #naive = obj.last_modified
                    #local_dt = local.localize(naive, is_dst=None)
                    utc_datetime = datetime.datetime.utcnow()
                    UTCTimeNow = utc_datetime.strftime("%Y-%m-%d %H:%M:%S")
                    L.append(dict(fileName=obj.key, lastModified=obj.last_modified, fileSize=obj.content_length))
                return render_template('index.html', L=L, bucketName=bucketName)
            else:
                return 'Incorrect Password'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

################ UPLOAD LOGIC #################
@app.route('/upload', methods=['POST', 'GET'])
def upload():
    if request.method == 'POST':
        file = request.files['file']
        fileName = file.filename
        filePath = os.path.abspath(fileName)
        userName = request.form['bucketName'][:-6]
        print userName
        if file and allowed_file(fileName):
        # Get the contents of file being uploaded
            data = file.read()
            fileSize = int(len(data))
            print fileSize
            cursor = conn.cursor()
            cursor.callproc('get_quota',(userName, fileName))
            # cursor.execute('SELECT TotalQuota, UsedQuota FROM Locations.User WHERE Name = %s limit 1', (userName))
            rows = cursor.fetchall()
            cursor.close()
            for row in rows:
                TotalQuota = row[0]
                UsedQuota = row[1]
            LeftQuota = int(TotalQuota) - int(UsedQuota)
            print LeftQuota
            if LeftQuota > int(fileSize):
                cursor = conn.cursor()
                print 'executing query'
                cursor.callproc('update_quota',(userName,fileSize))
                conn.commit()
                cursor.close()
                # Uploading the object to S3
                s3.Bucket(request.form['bucketName']).put_object(Key=fileName, Body=data)
                return '<b>File Uploaded</b>'
            else:
                return '<b>File not Uploaded, Over Quota</b>'
        else:
            return '<b>File not Uploaded, not an Image File</b>'

################ DOWNLOAD LOGIC #################
@app.route('/download', methods=['POST', 'GET'])
def download():
    if request.method == 'POST':
        fileName = request.form['fileID']
        save_path = '/Users/Swaroop/Downloads'
        completeName = os.path.join(save_path, fileName)
        # Get the object 
        obj = s3.Object(bucket_name=request.form['bucketName'], key=fileName)
        responseObj = obj.get()
        # Get the data from obj
        data = responseObj['Body'].read()
        # Write to a file
        file1 = open(completeName, "wb")
        file1.write(data)
        file1.close()
        # Download thingy in browser
        return send_from_directory(
          '/Users/Swaroop/Downloads', 
          fileName, 
          as_attachment=True) 
    
################ DELETE LOGIC #################
@app.route('/delete', methods=['POST', 'GET'])
def delete():
    if request.method == 'POST':
        fileName = request.form['fileID']
        userName = request.form['bucketName'][:-6]
        # Get the object
        obj = s3.Object(bucket_name=request.form['bucketName'], key=fileName)
        fileSize = obj.content_length
        cursor = conn.cursor()
        cursor.callproc('decrease_quota',(userName,fileSize))
        conn.commit()
        cursor.close()
        # Delete the object
        obj.delete()
        return '<b>File Deleted</b>'

if __name__ == '__main__':
  app.run(debug=True)
