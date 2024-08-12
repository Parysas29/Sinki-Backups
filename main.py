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

def get_file_info(file_path, hash_algorithm='md5'):
    try:
        # Calculate hash
        file_hash = calculate_hash(file_path, hash_algorithm)

        # Get relative path
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
    # Obtain File Info for storage in the manifest file
    file_info_list = []
    for file_path in file_list:
        file_info = get_file_info(file_path, "md5")
        debug_print(f"File info: {file_info}")
        if file_info:
            file_info_list.append(file_info)










def main():
    pre_file_path = './config/pre-operations.csv'
    #pre_operations(pre_file_path)
    operation_file_path = './config/backup-operations.csv'
    compare_files(operation_file_path)

if __name__ == "__main__":
    main()