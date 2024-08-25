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
import lzma
import shutil
import subprocess
import hashlib
import os
import json
from filesplit.split import Split
from base64 import b64encode, b64decode
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import time
from datetime import datetime

DEBUG = True  # Set this to False to disable debug messages

def debug_print(message):
    log_file_path = "./logs/debug.log"  # Specify the path to your log file
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Get the current timestamp

    # Write the message to the log file
    with open(log_file_path, "a") as log_file:
        log_file.write(f"[{timestamp}] {message} \n")

    # Print the message to the console if DEBUG is True
    if DEBUG:
        print(f"[{timestamp}] {message} \n")

def pre_operations(file_path):
    global_switches = "--bwlimit 20M:2G --fast-list --multi-thread-streams 10 --delete-during -P"
    
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            # Print the headers to debug
            headers = reader.fieldnames
            debug_print(f"pre_operations: CSV Headers: {headers}")
            
            for row in reader:
                # Print the current row to debug
                debug_print(f"pre_operations: Current row: {row}")
                
                operation = row.get('operation')
                if operation is None:
                    debug_print("pre_operations: Error: 'operation' key not found in the row.")
                    continue
                
                src = row.get('scr', '')
                dst = row.get('dst', '')
                
                if operation == "rclone-dedupe":
                    cmd = f"rclone dedupe rename {dst}"
                    debug_print(f"pre_operations: Executing: {cmd}")
                    subprocess.run(cmd, shell=True)
                
                elif operation == "rclone-sync-google":
                    local_switches = "--drive-acknowledge-abuse"
                    cmd = f"rclone sync {global_switches} {local_switches} {src} {dst}"
                    debug_print(f"pre_operations: Executing: {cmd}")
                    subprocess.run(cmd, shell=True)
                
                elif operation == "rclone-sync-onedrive":
                    local_switches = "--onedrive-delta"
                    cmd = f"rclone sync {global_switches} {local_switches} {src} {dst}"
                    debug_print(f"pre_operations: Executing: {cmd}")
                    subprocess.run(cmd, shell=True)
                
                else:
                    debug_print(f"pre_operations: Unknown operation: {operation}")
    except FileNotFoundError:
        debug_print(f"pre_operations: Error: The file '{file_path}' was not found.")
    except Exception as e:
        debug_print(f"pre_operations: An unexpected error occurred: {e}")


def calculate_hash(file_path, algorithm='md5'):
    calculate_hash = ""
    try:
        # Check if the algorithm is supported
        if algorithm not in hashlib.algorithms_available:
            raise ValueError(f"calculate_hash: Unsupported hash algorithm: {algorithm}")

        hash_func = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        calculate_hash = hash_func.hexdigest()
    except Exception as e:
        debug_print(f"calculate_hash: An error occurred while calculating the hash for '{file_path}': {e}")
        calculate_hash = hash_func.hexdigest()
    return calculate_hash

def get_file_info(file_path, hash_algorithm='md5', src_dir=None, dst_dir=None):
    try:
        debug_print(f"get_file_info: Processing file: {file_path}")
        # Calculate hash
        file_hash = calculate_hash(file_path, hash_algorithm)

        # Get relative path
        if src_dir:
            relative_path = os.path.relpath(file_path, src_dir)
            # Remove any ".." segments from the relative path
            relative_path = os.path.normpath(relative_path).replace("..\\", "").replace("../", "")
            relative_path = os.path.normpath("./" + relative_path)
            debug_print(f"get_file_info: Relative path from get_file_info: {relative_path}")
        else:
            relative_path = os.path.relpath(file_path)
            debug_print(f"get_file_info: Relative path from get_file_info: {relative_path}")

        # Get last modification time
        last_mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

        # Get file length
        file_length = os.path.getsize(file_path)

        file_info = {
            "Hash": file_hash,
            "RelativePath": relative_path,
            "LastModificationTime": last_mod_time,
            "Length": file_length
        }

    except Exception as e:
        debug_print(f"get_file_info: An error occurred while processing the file '{file_path}': {e}")
        file_info = None

    return file_info


def compare_files(file_path):
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            # Print the headers to debug
            headers = reader.fieldnames
            debug_print(f"compare_files: CSV Headers: {headers}")

            for row in reader:
                # Print the current row to debug
                debug_print(f"compare_files: Current row: {row}")
            
                src = row.get('src', '').strip()
                dst = row.get('dst', '').strip()
                debug_print(f"compare_files: Source directory: {src}")
                debug_print(f"compare_files: Destination directory: {dst}")
            
                manifest_file = "hazbackup.manifest"
                manifest_file_path = os.path.normpath(os.path.join(src, manifest_file))
                debug_print(f"compare_files: Manifest file path: {manifest_file_path}")
            
                if os.path.exists(manifest_file_path):
                    debug_print(f"compare_files: Manifest file already exists for source directory: {src}")
                else:
                    debug_print(f"compare_files: No manifest file found for source directory: {src}")
                    # Start Initial Backup
                    initial_backup(src, dst, manifest_file_path)
    except Exception as e:
        debug_print(f"compare_files: An error occurred while processing the file '{file_path}': {e}")
    


def initial_backup(src, dst, manifest_file_path):
    dst = os.path.normpath(dst)
    debug_print(f"initial_backup: Starting initial backup for source directory: {src}")
    debug_print(f"initial_backup: Destination directory: {dst}")

    # Check if the source directory exists
    if not os.path.exists(src):
        debug_print(f"initial_backup: Source directory '{src}' does not exist.")
        return
    
    # Check if the destination directory exists or create it
    if not os.path.exists(dst):
        os.makedirs(dst)
        debug_print(f"initial_backup: Destination directory '{dst}' created.")

    # Initialize an empty list to store file paths
    file_list = []

    # Walk through the source directory
    for root, dirs, files in os.walk(src):
        for file in files:
            file_path = os.path.join(root, file)
            file_list.append(file_path)
            debug_print(f"initial_backup: File path added: {file_path}")
    
    # Obtain File Info for storage in the manifest file
    file_info_list = []
    for file_path in file_list:
        debug_print(f"initial_backup: Processing file in for loop: {file_path}")
        file_info = get_file_info(file_path, "md5", src)
        debug_print(f"initial_backup: File info: {file_info}")
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
                debug_print("initial_backup: File info appended to the manifest file.")
            except Exception as e:
                debug_print(f"initial_backup: An error occurred while writing to the manifest file: {e}")
                
        debug_print("initial_backup: Checking Input for add_backup:" + file_path +" | "+ dst +" | "+ file_info['RelativePath'])
        add_backup(file_path, dst, file_info['RelativePath'], file_info['Hash'], file_info['Length'])

def calculate_chunked_hash(file_stream, chunk_size=4096):
    # Calculate the hash of the file in chunks
    hash_object = hashlib.md5()
    for chunk in iter(lambda: file_stream.read(chunk_size), b""):
        hash_object.update(chunk)
    return hash_object.hexdigest()

def add_backup(src, dst, relative_path, file_hash, file_length):
    debug_print(f"add_backup: Adding backup for file: {src}")
    debug_print(f"add_backup: Destination directory: {dst}")
    debug_print(f"add_backup: Relative path: {relative_path}")

    # Combine dst and relative_path to get the destination file path
    dst_file = os.path.join(dst, relative_path)
    
    # Check if the destination file already exists
    if os.path.exists(dst_file):
        debug_print(f"add_backup: Destination file '{dst_file}' already exists.")
        return

    # Handle long paths by using the \\?\ prefix
    if os.name == 'nt':
        src = f"\\\\?\\{os.path.abspath(src)}"
        dst_file = f"\\\\?\\{os.path.abspath(dst_file)}"

    # Ensure the destination directory exists
    os.makedirs(os.path.dirname(dst_file), exist_ok=True)

    # Copy, compress, split, and encrypt the file
    current_working_file = dst_file

    # Copy the source file to the destination directory
    copy_current_file(src, current_working_file, file_hash)

    # Compress the file if it meets the size and extension criteria
    # return the compressed file path
    current_working_file = compress_current_file(current_working_file, file_hash, file_length)
    debug_print(f"add_backup: Returning from compress_current_file: {current_working_file}")
    
    # Split the file if it exceeds 4GB
    current_working_file = split_current_file(current_working_file)
    debug_print(f"add_backup: Returning from split_current_file: {current_working_file}")

    prepare_files_for_encryption(current_working_file)

    return


def copy_current_file(src, current_working_file, file_hash):
    # Copy the source file to the destination directory
    try:
        for attempt in range(4):
            shutil.copy2(src, current_working_file)
            debug_print(f"copy_current_file: File copied to destination: {current_working_file}")

            # Verify the hash of the copied file
            copied_hash = calculate_hash(current_working_file)
            if copied_hash == file_hash:
                debug_print("copy_current_file: Hash verification successful. File copied successfully.")
                break
            else:
                debug_print("copy_current_file: Hash verification failed. Retrying... (Attempt {})".format(attempt + 1))
    except Exception as e:
        debug_print(f"copy_current_file: An error occurred while copying the file: {e}")
    return

def compress_current_file(current_working_file, file_hash, file_length):
    file_ext = os.path.splitext(current_working_file)[1]
    if file_ext and not os.path.basename(current_working_file).startswith('.'):
        # Remove the dot from the file extension
        file_ext = file_ext[1:]
    else:
        # If no file extension exists or the file starts with a dot, store current_working_file directly
        file_ext = '.' if os.path.basename(current_working_file).startswith('.') else "."
    # Check the size of the file
    debug_print(f"compress_current_file: File size: {file_length} bytes")

    # Compress the file if it meets the size and extension criteria
    file_not_compress = ['jpeg', 'jpg', 'gif', 'png',
                         'bmp', 'tiff', 'tif', 'avi',
                         'mp4', 'avi', 'mpeg', 'mp3',
                         'wav', 'flac', 'mkv', 'pdf',
                         'zip', 'rar', '7z', 'gz',
                         'tar', 'iso']
    if file_length >= 120 and (file_ext not in file_not_compress or file_ext == '.'):
        for attempt in range(4):
            try:
                # Compress the file using LZMA
                with open(current_working_file, "rb") as f_in:
                    with lzma.open(current_working_file + ".xz", "wb", format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                        # Close the compression stream
                    f_out.close()

                    debug_print(f"compress_current_file: File compressed: {current_working_file}")
            except Exception as e:
                debug_print(f"compress_current_file: An error occurred while compressing the file: {e}")
                continue
            try:
                # Decompress the file into memory with chunking to verify integrity
                with open(current_working_file + ".xz", "rb") as compressed_file:
                    with lzma.open(compressed_file, "rb") as decompressed_file:
                        # Calculate hash from decompressed data in chunks
                        decompressed_hash = calculate_chunked_hash(decompressed_file)
                        # Compare the decompressed hash with the original file hash
                        if decompressed_hash == file_hash:
                            debug_print("compress_current_file: Hash verification successful. Decompressed data matches the original file.")
                            # Remove the original uncompressed file after successful compression
                            os.remove(current_working_file)
                            debug_print(f"compress_current_file: Original file removed: {current_working_file}")
                            current_working_file = current_working_file + ".xz"
                            break
                        else:
                            debug_print("compress_current_file: Hash verification failed. Retrying... (Attempt {})".format(attempt + 1))
            except Exception as e:
                debug_print(f"compress_current_file: An error occurred while decompressing or verifying the file: {e}")
    else:
        debug_print("compress_current_file: File size is less than 120 bytes or is a type that don't compress well. Skipping Compression.")
    return current_working_file

def split_current_file(current_working_file):
    """
    Splits the given file into 4GB chunks if its size exceeds 4GB.
    
    Parameters:
    current_working_file (str): The path to the file to be split.
    
    Returns:
    str: The path to the split manifest file if the file is split, 
         otherwise the original file path.
    """
    # Get the size of the current file
    current_file_size = os.path.getsize(current_working_file)
    debug_print(f"split_current_file: Current file size: {current_file_size} bytes")
    
    # Check if the file size exceeds 4GB
    if current_file_size > 4 * 1024 * 1024 * 1024:
        # Get the directory of the current file
        dst_file_dir = os.path.dirname(current_working_file)
        debug_print(f"split_current_file: Directory Path: {dst_file_dir}")
        
        # Initialize the Split object with the current file and its directory
        split = Split(current_working_file, dst_file_dir)
        
        # Create the manifest file name by appending ".man" to the original file name
        splitManfile = os.path.basename(current_working_file) + ".man"
        debug_print(f"split_current_file: Split Manifest File: {splitManfile}")
        
        # Set the manifest file name in the Split object
        split.manfilename = splitManfile
        
        # Split the file into chunks of 4GB each
        split.bysize(size=4 * 1024 * 1024 * 1024)
        debug_print(f"split_current_file: File split into 4GB chunks: {current_working_file}")
        
        # Return the path to the split manifest file
        current_working_file = os.path.join(dst_file_dir, splitManfile)
    else:
        # If the file size is less than or equal to 4GB, no splitting is done
        print("split_current_file: Compressed file does not exist. Skipping splitting.")
    
    # Return the original file path if no splitting is done
    return current_working_file

def prepare_files_for_encryption(current_working_file):
    # Check if the .man file exists
    if current_working_file.endswith(".man"):
        man_file_path = current_working_file
        debug_print(f"prepare_files_for_encryption: Manifest file '{man_file_path}' from the split command exists.")

        # Read the contents of the .man file
        with open(man_file_path, 'r') as man_file:
            lines = man_file.readlines()

        lines = lines[1:]  # Skip the first line (header)

        filenames = [line.split(',')[0] for line in lines]
        current_working_list = []
        for filename in filenames:
            debug_print(f"prepare_files_for_encryption: Current Value of filename: {filename}")
            # Append the full file path to each filename
            full_file_path = os.path.join(os.path.dirname(current_working_file), filename)
            debug_print(f"prepare_files_for_encryption: Full file path as created by the split manifest file: {full_file_path}")
            current_working_list.append(full_file_path)

        # Append .man file also
        current_working_list.append(man_file_path)

        # Encrypt the files
        for file in current_working_list:
            encrypt_current_file(file)

    else :
        debug_print(f"prepare_files_for_encryption: No Manifest file found moving onto encryption.")
        encrypt_current_file(current_working_file)

    return

def get_optimal_iterations(password, salt, target_time_ms=25):
    # Check if the iterations file exists
    iterations_file = os.path.normpath('./config/iterations.json')
    if os.path.exists(iterations_file):
        with open(iterations_file, 'r') as file:
            data = json.load(file)
            return data['iterations']

    # Measure the time for a fixed number of iterations
    test_iterations = 1000
    elapsed_time_ms = 0

    # Ensure elapsed_time_ms is non-zero by increasing test_iterations if necessary
    while elapsed_time_ms == 0:
        start_time = time.time()
        hashlib.pbkdf2_hmac('sha256', password, salt, test_iterations, dklen=16)
        end_time = time.time()
        elapsed_time_ms = (end_time - start_time) * 1000
        if elapsed_time_ms == 0:
            test_iterations *= 2  # Double the test iterations if time is too short

    # Calculate the required iterations to achieve the target time
    optimal_iterations = int((target_time_ms / elapsed_time_ms) * test_iterations)

    # Store the optimal iterations in the JSON file
    with open(iterations_file, 'w') as file:
        json.dump({'iterations': optimal_iterations}, file)

    return optimal_iterations


def encrypt_current_file(current_working_file):
    debug_print("encrypt_current_file: " + current_working_file)

    # Calculate the MD5 hash of the original file
    original_hash = calculate_hash(current_working_file)
    debug_print(f"encrypt_current_file: Original file hash: {original_hash}")
    
    # Read the contents of the file
    with open(current_working_file, 'rb') as file:
        plaintext = file.read()
    
    # User-defined password
    password = 'ThisIsASecretKey'.encode('utf-8')
    
    # Generate a random salt
    salt = get_random_bytes(16)
    
    # Get the optimal number of iterations
    iterations = get_optimal_iterations(password, salt)
    debug_print(f"encrypt_current_file: Optimal iterations: {iterations}")
    
    # Derive the key using PBKDF2
    key = hashlib.pbkdf2_hmac('sha256', password, salt, iterations, dklen=16)  # AES-128 requires a 16-byte key

    # Create AES-GCM cipher
    cipher = AES.new(key, AES.MODE_GCM)
    cipher.update(b"header")
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)

    # Prepare the data to be saved
    jk = ['nonce', 'header', 'ciphertext', 'tag', 'salt', 'iterations']
    jv = [b64encode(x).decode('utf-8') for x in (cipher.nonce, b"header", ciphertext, tag, salt)]
    jv.append(iterations)
    result = json.dumps(dict(zip(jk, jv)))

    # Save the encrypted data to a new file
    encrypted_file_path = current_working_file + '.enc'
    with open(encrypted_file_path, 'w') as encrypted_file:
        encrypted_file.write(result)

    

# Decrypt the file to verify
    try:
        with open(encrypted_file_path, 'r', encoding='utf-8') as encrypted_file:
            encrypted_data = json.load(encrypted_file)
        
        nonce = b64decode(encrypted_data['nonce'])
        header = b64decode(encrypted_data['header'])
        ciphertext = b64decode(encrypted_data['ciphertext'])
        tag = b64decode(encrypted_data['tag'])
        salt = b64decode(encrypted_data['salt'])
        iterations = encrypted_data['iterations']

        key = hashlib.pbkdf2_hmac('sha256', password, salt, iterations, dklen=16)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        cipher.update(header)
        decrypted_plaintext = cipher.decrypt_and_verify(ciphertext, tag)

        # Calculate the MD5 hash of the decrypted data
        decrypted_hash = hashlib.md5(decrypted_plaintext).hexdigest()
        debug_print(f"encrypt_current_file: Decrypted file hash: {decrypted_hash}")

        # Verify the integrity of the decrypted data
        if original_hash == decrypted_hash:
            debug_print("encrypt_current_file: File integrity verified. Deleting original file.")
            os.remove(current_working_file)
        else:
            debug_print("encrypt_current_file: File integrity verification failed.")
    except Exception as e:
        debug_print(f"encrypt_current_file: An error occurred while decrypting or verifying the file: {e}")

    debug_print("encrypt_current_file: File encrypted and saved to: " + encrypted_file_path)
    return encrypted_file_path

def decrypt_current_file(encrypted_file_path):
    debug_print("decrypt_current_file: " + encrypted_file_path)
    
    # Read the encrypted data
    with open(encrypted_file_path, 'r') as encrypted_file:
        data = json.load(encrypted_file)
    
    # Extract the components
    nonce = b64decode(data['nonce'])
    header = b64decode(data['header'])
    ciphertext = b64decode(data['ciphertext'])
    tag = b64decode(data['tag'])
    salt = b64decode(data['salt'])
    iterations = data['iterations']
    
    # User-defined password
    password = 'ThisIsASecretKey'.encode('utf-8')
    
    # Derive the key using PBKDF2
    key = hashlib.pbkdf2_hmac('sha256', password, salt, iterations, dklen=16)  # AES-128 requires a 16-byte key

    # Create AES-GCM cipher
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(header)
    
    # Decrypt and verify the data
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    
    # Save the decrypted data to a new file
    decrypted_file_path = encrypted_file_path.replace('.enc', '.dec')
    with open(decrypted_file_path, 'wb') as decrypted_file:
        decrypted_file.write(plaintext)

    debug_print("decrypt_current_file: File decrypted and saved to: " + decrypted_file_path)

def main():
    pre_file_path = './config/pre-operations.csv'
    #pre_operations(pre_file_path)
    operation_file_path = './config/backup-operations.csv'
    compare_files(operation_file_path)

    #current = os.path.normpath("A:\\test\\Vid\\homevid(1).mkv")
    #prepare_files_for_encryption(current)

if __name__ == "__main__":
    main()