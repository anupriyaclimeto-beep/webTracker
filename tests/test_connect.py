import os
import sys
from dotenv import load_dotenv

load_dotenv()

ok = True

# Test Postgres
try:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv('SUPABASE_HOST'),
        port=os.getenv('SUPABASE_PORT'),
        dbname=os.getenv('SUPABASE_DB'),
        user=os.getenv('SUPABASE_USER'),
        password=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_PASSWORD'),
        sslmode='require',
        connect_timeout=5,
    )
    conn.close()
    print('POSTGRES: OK')
except Exception as e:
    print('POSTGRES: ERROR', e)
    ok = False

# Test Cloudinary
try:
    import cloudinary
    import cloudinary.uploader
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    if cloud_name:
        cloud_name = cloud_name.strip('\"')
    if api_key:
        api_key = api_key.strip('\"')
    if api_secret:
        api_secret = api_secret.strip('\"')
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
    import io
    res = cloudinary.uploader.upload(io.BytesIO(b'test'), resource_type='raw', folder='webtracker_test', public_id='health_check_test', overwrite=True)
    url = res.get('secure_url')
    if url:
        print('CLOUDINARY: OK')
    else:
        print('CLOUDINARY: ERROR - no url in response')
        ok = False
except Exception as e:
    print('CLOUDINARY: ERROR', e)
    ok = False

sys.exit(0 if ok else 2)

