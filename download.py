# Python script to download files from the Wisconsin Historic Aerial Imagery archive
# Jim Lacy, Wisconsin State Cartographer's Office
# January 2025

# Important: the requests and tqdm packages need to be installed before you can proceed.
# pip install requests tqdm

# Note: This script is designed for Python 3.x. 

# Find the WI Historic Aerial Imagery index at  https://uw-mad.maps.arcgis.com/home/item.html?id=15aa61bed9cd48da9116d1d45d0b481b

# Syntax: python download.py [csv file containing list of urls] [output directory]
# Example: python download.py files.csv c:\temp

import requests
import os
import csv
import argparse
from tqdm import tqdm

def read_data_from_csv(csv_file):
    # Read the CSV file extracted from the WI Historical Aerial Imagery feature service
    # For this example, we only care about the tiff_download_url field
    # other fields are ignored
    
    urls = []
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            urls.append({
                'tiff_download_url': row['tiff_download_url']
                })
                # The above is slightly more complicated than necessary for simple urls, but it allows flexibility to
                # add other fields from the csv if desired.  For example:
                #urls.append({
                #'tiff_download_url': row['tiff_download_url'],
                #'tiff_filesize_MB': row['tiff_filesize_MB']
                #})
    return urls


def download_file(url, output_directory):
    # Download the requested file and dump into the output_directory
    # Chunks are used as this is allegedly more reliable for large files
    # Also makes it possible to use tqdm so the user can view download status
    
    # Construct the output filename from URL
    filename = os.path.join(output_directory, url['tiff_download_url'].split('/')[-1])
    
    print(f"Downloading {url['tiff_download_url']}...")
    
    block_size = 1024 # 1 Kilobyte
    
    try:      
        with requests.get(url['tiff_download_url'], stream=True) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))            
            t = tqdm(total=total_size, unit='iB', unit_scale=True)
            with open(filename, 'wb') as file:
                for chunk in response.iter_content(chunk_size=block_size):
                    t.update(len(chunk))
                    file.write(chunk)
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {url['tiff_download_url']}: {e}")
  
# Define the main function
def main(input_csv, output_directory):

    # Create the output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)

    # Read URLs from the CSV file
    urls_to_download = read_data_from_csv(input_csv)

    # Loop through the list of urls to download
    for url in urls_to_download:
        download_file(url, output_directory)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download files from the WI Historic Aerial Imagery archive.")
    parser.add_argument('input_csv', type=str, help="Path to the input CSV file.")
    parser.add_argument('output_directory', type=str, help="Destination folder for files.")
    args = parser.parse_args()
    main(args.input_csv, args.output_directory)