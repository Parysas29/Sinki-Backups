""" ToDo:
1. Create initial backup script.
   - Operations will be determined by a CSV file with the following fields:
     1. Operation type
     2. Source directory
     3. Destination directory

2. Perform initial rclone operations on cloud services:
   - Run "rclone dedupe rename" for Google Drive files.
   - Sync all cloud locations to the main storage drive.

3. On the main storage drive:
   - Assign md5sum hashes to all files (if not already present).
   - Compress files and split archives if larger than 4GB.
   - Encrypt compressed files using AES-256-GCM.
   - Perform secure erase on unencrypted files post-processing.

4. On the main storage drive, use md5 hashes to:
   - Detect modified files for backup updates.
   - Identify deleted or newly added files.

Additional Steps:
5. Logging and Notifications:
   - Implement detailed logging for each operation (start time, end time, success/failure, error messages).
   - Set up notifications (email, SMS, etc.) for operation statuses.

6. Error Handling and Recovery:
   - Define error handling mechanisms (retries, alerts).
   - Create a recovery plan for failed operations (manual intervention steps).

7. Scheduling and Automation:
   - Schedule the script to run at regular intervals using Task Scheduler.
   - Ensure the script can handle incremental backups efficiently.

8. Security Considerations:
   - Securely store encryption keys (e.g., use a key management service).
   - Ensure secure transfer of data (e.g., use SFTP/HTTPS for remote transfers).

9. Verification and Integrity Checks:
   - Regularly verify backup integrity (e.g., periodic test restores).
   - Compare md5 hashes to ensure file integrity post-backup.

10. Documentation:
    - Maintain up-to-date documentation for the script (usage, configuration, troubleshooting).
    - Include version control for the script and associated files.
 """
import csv
import shutil
import subprocess
import hashlib
from datetime import datetime
import os
import json

DEBUG = True  # Set this to False to disable debug messages

def debug_print(message):
    if DEBUG:
        print(message)

def pre_operations(file_path):
    global_switches = "--bwlimit 20M:2G --fast-list --multi-thread-streams 10 --delete-during -P"
    
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            # Print the headers to debug
            headers = reader.fieldnames
            debug_print(f"CSV Headers: {headers}")
            
            for row in reader:
                # Print the current row to debug
                debug_print(f"Current row: {row}")
                
                operation = row.get('operation')
                if operation is None:
                    debug_print("Error: 'operation' key not found in the row.")
                    continue
                
                src = row.get('scr', '')
                dst = row.get('dst', '')
                
                if operation == "rclone-dedupe":
                    cmd = f"rclone dedupe rename {dst}"
                    debug_print(f"Executing: {cmd}")
                    subprocess.run(cmd, shell=True)
                
                elif operation == "rclone-sync-google":
                    local_switches = "--drive-acknowledge-abuse"
                    cmd = f"rclone sync {global_switches} {local_switches} {src} {dst}"
                    debug_print(f"Executing: {cmd}")
                    subprocess.run(cmd, shell=True)
                
                elif operation == "rclone-sync-onedrive":
                    local_switches = "--onedrive-delta"
                    cmd = f"rclone sync {global_switches} {local_switches} {src} {dst}"
                    debug_print(f"Executing: {cmd}")
                    subprocess.run(cmd, shell=True)
                
                else:
                    debug_print(f"Unknown operation: {operation}")
    except FileNotFoundError:
        debug_print(f"Error: The file '{file_path}' was not found.")
    except Exception as e:
        debug_print(f"An unexpected error occurred: {e}")


def calculate_hash(file_path, algorithm='md5'):
    try:
        # Check if the algorithm is supported
        if algorithm not in hashlib.algorithms_available:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")

        hash_func = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except Exception as e:
        debug_print(f"An error occurred while calculating the hash for '{file_path}': {e}")
        return None

def get_file_info(file_path, hash_algorithm='md5', src_dir=None, dst_dir=None):
    try:
        debug_print(f"Processing file: {file_path}")
        # Calculate hash
        file_hash = calculate_hash(file_path, hash_algorithm)

        # Get relative path
        if src_dir:
            relative_path = os.path.relpath(file_path, src_dir)
            # Remove any ".." segments from the relative path
            relative_path = os.path.normpath(relative_path).replace("..\\", "").replace("../", "")
            relative_path = os.path.normpath("./" + relative_path)
            debug_print(f"Relative path from get_file_info: {relative_path}")
        else:
            relative_path = os.path.relpath(file_path)
            debug_print(f"Relative path from get_file_info: {relative_path}")

        # Get last modification time
        last_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

        # Get file length
        file_length = os.path.getsize(file_path)

        return {
            "Hash": file_hash,
            "RelativePath": relative_path,
            "LastModificationTime": last_mod_time,
            "Length": file_length
        }
    except Exception as e:
        debug_print(f"An error occurred while processing the file '{file_path}': {e}")
        return None

def compare_files(file_path):
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            # Print the headers to debug
            headers = reader.fieldnames
            debug_print(f"CSV Headers: {headers}")

            for row in reader:
                # Print the current row to debug
                debug_print(f"Current row: {row}")
            
                src = row.get('src', '').strip()
                dst = row.get('dst', '').strip()
                debug_print(f"Source directory: {src}")
                debug_print(f"Destination directory: {dst}")
            
                manifest_file = "hazbackup.manifest"
                manifest_file_path = os.path.normpath(os.path.join(src, manifest_file))
                debug_print(f"Manifest file path: {manifest_file_path}")
            
                if os.path.exists(manifest_file_path):
                    debug_print(f"Manifest file already exists for source directory: {src}")
                else:
                    debug_print(f"No manifest file found for source directory: {src}")
                    # Start Initial Backup
                    initial_backup(src, dst, manifest_file_path)


    except Exception as e:
        debug_print(f"An error occurred while processing the file '{file_path}': {e}")
    


def initial_backup(src, dst, manifest_file_path):
    dst = os.path.normpath(dst)
    debug_print(f"Starting initial backup for source directory: {src}")
    debug_print(f"Destination directory: {dst}")

    # Check if the source directory exists
    if not os.path.exists(src):
        debug_print(f"Source directory '{src}' does not exist.")
        return
    
    # Check if the destination directory exists or create it
    if not os.path.exists(dst):
        os.makedirs(dst)
        debug_print(f"Destination directory '{dst}' created.")

    # Initialize an empty list to store file paths
    file_list = []

    # Walk through the source directory
    for root, dirs, files in os.walk(src):
        for file in files:
            file_path = os.path.join(root, file)
            file_list.append(file_path)
            debug_print(f"File path added: {file_path}")    
    # Obtain File Info for storage in the manifest file
    file_info_list = []
    for file_path in file_list:
        debug_print(f"Processing file in for loop: {file_path}")
        file_info = get_file_info(file_path, "md5", src)
        debug_print(f"File info: {file_info}")
        if file_info:
            file_info_list.append(file_info)
            # Append file info to the manifest file
            try:
                # Read existing data from the JSON file
                if os.path.exists(manifest_file_path):
                    with open(manifest_file_path, mode='r') as manifest_file:
                        existing_data = json.load(manifest_file)
                else:
                    existing_data = []
            
                # Append new file info to the existing data
                existing_data.extend(file_info_list)

            
                # Write the updated data back to the JSON file
                with open(manifest_file_path, mode='w') as manifest_file:
                    json.dump(existing_data, manifest_file, indent=4)
                debug_print("File info appended to the manifest file.")
            except Exception as e:
                debug_print(f"An error occurred while writing to the manifest file: {e}")
        debug_print("Checking Input for add_backup:" + file_path +" | "+ dst +" | "+ file_info['RelativePath'])
        add_backup(file_path, dst, file_info['RelativePath'], file_info['Hash'])

def add_backup(src, dst, relative_path, file_hash):

    #debug_print(f"Adding backup for file: {src}")
    #debug_print(f"Destination directory: {dst}")
    #debug_print(f"Relative path: {relative_path}")
    # Combine dst and relative_path to get the destination file path
    dst_file = os.path.join(dst, relative_path)
    
    # Check if the destination file already exists
    if os.path.exists(dst_file):
        debug_print(f"Destination file '{dst_file}' already exists.")
        return

    # Copy the source file to the destination directory
    try:
        for attempt in range(4):
            shutil.copy2(src, dst_file)
            debug_print(f"File copied to destination: {dst_file}")

            # Verify the hash of the copied file
            copied_hash = calculate_hash(dst_file)
            if copied_hash == file_hash:
                debug_print("Hash verification successful. File copied successfully.")
                break
            else:
                debug_print("Hash verification failed. Retrying... (Attempt {})".format(attempt + 1))
    except Exception as e:
        debug_print(f"An error occurred while copying the file: {e}")
    # Now I need to add the compression bit and the encryption bit.
    # As this function will be used throughout the script
    # I am going to create a new function for this.




def main():
    pre_file_path = './config/pre-operations.csv'
    #pre_operations(pre_file_path)
    operation_file_path = './config/backup-operations.csv'
    compare_files(operation_file_path)

if __name__ == "__main__":
    main()