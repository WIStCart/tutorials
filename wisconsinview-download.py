"""
Python 3.x script to bulk download files from the WisconsinView Data archive maintained by the Robinson Map Library and State Cartographer's Office, University of Wisconsin-Madison.  For assistance, contact help@sco.wisc.edu.

Jim Lacy, Wisconsin State Cartographer's Office
June 2025

**** To run this script you will need the Python boto3 and tqdm libraries:
pip install boto3 tqdm

Interactive usage:
python wisconsinview-download.py
Enter the remote folder to download:  /lidar/Milwaukee/Milwaukee_2020_County_Delivery/Raster_DSM_Hillshade/
Enter path to your local download folder: c:\temp

Commandline usage: 
python wisconsinview-download.py -f /lidar/Milwaukee/Milwaukee_2020_County_Delivery/Raster_DSM_Hillshade/ -d c:\temp -t 10

Where:
remote folder = folder in WisconsinView S3 bucket that contains data you wish to download (Note: *everything* in this folder and below will be downloaded)
download folder = folder on your local computer where you want to save the downloaded files.
threads = number of simultaneous downloads to use. 10 is a good number for most systems.

Caveats:
Due to the inherent nature of threading, the script sometimes does not respond to ctrl-c requests when running.  If this happens, the only option is to kill the Python window.

"""

import boto3
from tqdm import tqdm
import os
import sys
import concurrent.futures
import time
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
import argparse
import threading

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def list_all_objects(s3, bucket_name, folder):
    paginator = s3.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=folder)

    all_objects = []
    for page in page_iterator:
        contents = page.get('Contents', [])
        all_objects.extend(contents)
    return all_objects

def download_single_object(s3, bucket_name, obj, download_path, cancel_event, max_retries=3):
    key = obj['Key']
    if key.endswith('/'):
        return False, 0  # Skip folders

    file_path = os.path.join(download_path, *key.split('/'))
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    if os.path.exists(file_path):
        local_size = os.path.getsize(file_path)
        if local_size >= obj['Size']:
            #print(f"[SKIP] Already downloaded: {key}")
            return False, 0

    #print(f"[START] Downloading: {key}")

    for attempt in range(1, max_retries + 1):
        if cancel_event.is_set():
            return False, 0  # Cancelled

        try:
            with open(file_path, 'wb') as f:
                response = s3.get_object(Bucket=bucket_name, Key=key)
                for chunk in response['Body'].iter_chunks(chunk_size=8192):
                    if cancel_event.is_set():
                        return False, 0  # Cancelled
                    f.write(chunk)
            return True, obj['Size']  # Success
        except ClientError as e:
            if attempt == max_retries:
                print(f"[FAIL] {key} failed after {max_retries} attempts: {e}")
                return False, 0
            else:
                print(f"[RETRY] Attempt {attempt}/{max_retries} for {key}...")
                time.sleep(10 + (attempt - 1) * 5)

def download_objects(bucket_name, folder, download_path, endpoint_url, max_threads=10):
    config = Config(
        signature_version=UNSIGNED,
        retries={'max_attempts': 5, 'mode': 'standard'},
        read_timeout=120,
        connect_timeout=30
    )

    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        config=config
    )
    
    # standardize the input folder
    folder = folder.lstrip('/')
    if not folder.endswith('/'):
        folder += '/'

    objects = list_all_objects(s3, bucket_name, folder)
    if not objects:
        print(f"Error: No files found at {folder}")
        return
    
    # don't count folders, which end with /
    total_expected_files = len([obj for obj in objects if not obj['Key'].endswith('/')])
    print(f"Found {total_expected_files} file(s) to download using {max_threads} threads.\n")

    total_size = sum(obj['Size'] for obj in objects)
    downloaded_files = 0
    skipped_files = 0
    failed_files = 0
    total_bytes_downloaded = 0
    cancel_event = threading.Event()
    start_time = time.time()

    try:
        with tqdm(total=total_size, unit='B', unit_scale=True, desc="Downloading files", ascii=True) as pbar:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = [
                    executor.submit(download_single_object, s3, bucket_name, obj, download_path, cancel_event)
                    for obj in objects if not obj['Key'].endswith('/')
                ]
                for future in concurrent.futures.as_completed(futures):
                    if cancel_event.is_set():
                        break
                    try:
                        success, bytes_downloaded = future.result()
                        if success:
                            downloaded_files += 1
                            total_bytes_downloaded += bytes_downloaded
                        elif bytes_downloaded == 0:
                            skipped_files += 1
                        else:
                            failed_files += 1
                        pbar.update(bytes_downloaded)
                    except Exception as e:
                        print(f"[ERROR] {e}")
                        failed_files += 1
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Ctrl+C detected. Cancelling downloads...")
        cancel_event.set()
        executor.shutdown(wait=False, cancel_futures=True)
        sys.exit(1)

    elapsed_time = time.time() - start_time

    print("\nDownload Summary:")
    print(f"Total files found: {total_expected_files}")
    print(f"Files successfully downloaded: {downloaded_files}")
    print(f"Files skipped (already complete): {skipped_files}")
    print(f"Files failed (after retries): {failed_files}")
    print(f"Total data downloaded: {format_bytes(total_bytes_downloaded)}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download all files from specified folder in WisconsinView S3 bucket.")
    parser.add_argument('-f', '--folder', type=str, help="Remote folder to download (e.g., /lidar/Milwaukee/Milwaukee_2021_MMSD_Delivery/)")
    parser.add_argument('-d', '--download-path', type=str, help="Path to your local download folder")
    parser.add_argument('-t', '--threads', type=int, default=10, help="Number of parallel downloads (default 10)")
    args = parser.parse_args()

    bucket_name = "wsco-wisconsinview"
    endpoint_url = "https://web.s3.wisc.edu"

    folder = args.folder or input("Enter the remote folder to download (e.g., /lidar/Milwaukee/Milwaukee_2021_MMSD_Delivery/): ").lstrip('/')
    if not folder.endswith('/'):
        folder += '/'
    download_path = args.download_path or os.path.normpath(input("Enter path to your local download folder: "))

    # Validate and cap thread count
    if args.threads < 1:
        print("Number of threads must be at least 1. Defaulting to 1.")
        max_threads = 1
    elif args.threads > 20:
        print("Number of threads capped at 20 to prevent overload.")
        max_threads = 20
    else:
        max_threads = args.threads

    download_objects(bucket_name, folder, download_path, endpoint_url, max_threads)