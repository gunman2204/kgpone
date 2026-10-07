import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client('s3', region_name=os.getenv('AWS_DEFAULT_REGION'))
bucket = os.getenv('S3_BUCKET_NAME')

try:
    print(f"Testing access to bucket: {bucket}")
    s3.head_bucket(Bucket=bucket)
    print("Success: Bucket is accessible!")
except ClientError as e:
    print(f"Error: {e}")
    if e.response['Error']['Code'] == '403':
        print("Detailed Error: You do not have permission to access this bucket. It likely belongs to another AWS account.")
