<#
ToDo:
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
 #>

 function Pre-Operations {
    $data = Import-Csv -Path .\config\pre-config.csv
    $globalSwitches = "--bwlimit 20M:2G --fast-list --multi-thread-streams 10 --delete-during -P"

    foreach ($row in $data) {
        switch ($row.operation) {
            "rclone-dedupe" {
                $cmd = "rclone dedupe rename $($row.dst)"
                Write-Host "Executing: $cmd"
                Invoke-Expression $cmd
            }
            "rclone-sync-google" {
                $localSwitches = "--drive-acknowledge-abuse"
                $cmd = "rclone sync $globalSwitches $localSwitches $($row.scr) $($row.dst)"
                Write-Host "Executing: $cmd"
                Invoke-Expression $cmd
            }
            "rclone-sync-onedrive" {
                $localSwitches = "--onedrive-delta"
                $cmd = "rclone sync $globalSwitches $localSwitches $($row.scr) $($row.dst)"
                Write-Host "Executing: $cmd"
                Invoke-Expression $cmd
            }
            default {
                Write-Host "Unknown operation: $($row.operation)"
            }
        }
    }
}

function Compare-Files {
    $mainStorages = Get-Content -Path .\config\main-storages.txt
    # Read the file line by line
    ForEach ($Line in $mainStorages) {
        $drive = $Line.TrimEnd(":")  # Remove the colon from the drive letter
        $hashFile = "$drive-Hashes.csv"
        $hashFilePath = ".\logs\$hashFile"
        
        if (Test-Path -path $hashFilePath -PathType Leaf) {
            Write-Host "The file exists: $hashFilePath" -ForegroundColor Green
<#             $fileData = Import-Csv -Path $hashFilePath
            
            # Create a hashtable to store existing file data for quick lookup
            $existingFiles = @{}
            foreach ($item in $fileData) {
                $existingFiles[$item.RelativePath] = $item
            } #>
        }
        else {
            Write-Host "Hash file not found: $hashFilePath. Creating new hashes..." -ForegroundColor Yellow
            # Create directory for logs if it doesn't exist
            if (!(Test-Path -Path .\logs -PathType Container)) {
                New-Item -ItemType Directory -Path .\logs
            }
            # Write CSV header
            "Hash,RelativePath,LastModificationTime,Length" | Out-File -FilePath $hashFilePath -Encoding utf8
            # Get all files in the drive
            $files = Get-ChildItem -Path "$Line\" -Recurse -File
            foreach ($file in $files) {
                $csvLine = Get-FilesInfo("Y", $file)
                # Append the line to the CSV file
                Add-Content -Path $hashFilePath -Value $csvLine
            }
            Write-Host "Hash file created: $hashFilePath" -ForegroundColor Green
        }
        # No matter if the logs files existed or not we can begin the second part of comparing files for transfer here
        if (Test-Path -path $hashFilePath -PathType Leaf) {
            Write-Host "Copying $hashFilePath into a hashtable" -ForegroundColor Green
            $fileData = Import-Csv -Path $hashFilePath
            
            # Create a hashtable to store existing file data for quick lookup
            $existingFiles = @{}
            foreach ($item in $fileData) {
                $existingFiles[$item.RelativePath] = $item
            }
            #Write-Output $existingFiles
            
            # Run Get-FilesInfo with param set to "N"
            foreach ($file in $files) {
                $csvLine = Get-FilesInfo("N", $file)
                # Append the line to the CSV file
                Add-Content -Path $hashFilePath -Value $csvLine
            }
        }
    }
}
function Get-FilesInfo {
    param ($hashYN, $filename)
    if ($hashYN -eq "Y") {
        # Compute the MD5 hash
        $hash = (Get-FileHash -Algorithm MD5 -Path $file.FullName).Hash
    }
    # Create the relative path
    $relativePath = $file.FullName.Substring($Line.Length + 1)
    # Get the file Last Modification Time
    $lastModificationTime = $file.LastWriteTimeUtc
    # Get the file length
    $length = $file.Length
    # Prepare the CSV line
    $Line = "$hash,$relativePath,$lastModificationTime,$length"
	
    return $Line
}

#Pre-Operations
Compare-Files