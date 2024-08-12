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

function Get-FilesInfo {
    param (
        [string]$hashYN,
        [string]$file,
        [string]$Line
    )

    $hash = if ($hashYN -eq "Y") { Get-FileHash -Path $file -Algorithm SHA256 | Select-Object -ExpandProperty Hash } else { "" }
    $relativePath = $file.Substring($Line.Length)
    $lastModificationTime = (Get-Item $file).LastWriteTime
    $fileLength = (Get-Item $file).Length

    $fileInfo = @{
        Hash                 = $hash
        RelativePath         = $relativePath
        LastModificationTime = $lastModificationTime
        Length               = $fileLength
    }

    return $fileInfo
}


function Process-Line {
    param (
        [string]$srcDir
    )
    $manifest = "$($srcDir.Substring(0, 1))$(Split-Path -Path $srcDir -Leaf).manifest" -replace ' ', '_'
    Write-Host "Manifest: $manifest"
    $manifestFilePath = ".\logs\$manifest"
    
    return $manifestFilePath
}

function Add-Backup {
    param (
        [string]$file,
        [string]$srcDir,
        [string]$dstDir,
        [string]$expectedHash,
        [string]$logDir
    )
    # Check if the path is a file
    if (-not (Test-Path -Path $file -PathType Leaf)) {
        Write-Host "Skipping directory: $file"
        return
    }
    # Get the full path of the file
    $fullPath = (Get-Item $file).FullName
    
    # Calculate the relative path
    $relativePath = $fullPath.Substring($srcDir.Length).TrimStart('\')
    
    # Construct the destination path with the relative path
    $destinationPath = Join-Path -Path $dstDir -ChildPath $relativePath
    
    # Ensure the destination directory exists
    $destinationDir = Split-Path -Path $destinationPath -Parent
    if (-not (Test-Path -Path $destinationDir)) {
        New-Item -Path $destinationDir -ItemType Directory -Force
    }
    
    $maxRetries = 3
    $attempt = 0
    $success = $false
    Copy-Item -Path $fullPath -Destination $destinationPath -Force
    while ($attempt -lt $maxRetries -and -not $success) {
        # Copy the file to the backup location
        Copy-Item -Path $fullPath -Destination $destinationPath -Force
        
        # Verify the hash sum of the copied file
        $copiedFileHash = Get-FileHash -Path $destinationPath -Algorithm SHA256
        if ($copiedFileHash.Hash -eq $expectedHash) {
            Write-Host "File copied and verified successfully: $file"
            Start-Sleep -Milliseconds 25

            $success = $true 
        }
        else {
            Write-Host "Hash mismatch for file: $file. Attempt $($attempt + 1) of $maxRetries."
            $attempt++
        }
    }
    if ($success) {
        # Run additional code here if $success is true
            # Compress the file using 7zip
            $compressedFilePath = "$destinationPath.7z"
            $cmd = "7z"
            $zipargs = "a -t7z -m0=lzma2 -mx=9 -mfb=64 -md=32m -ms=on", "`"$compressedFilePath`"", "`"$destinationPath`""
            Write-Host "Compressing file: $file"
            Start-Process -FilePath $cmd -ArgumentList $zipargs -NoNewWindow -Wait
    } else {
        # Run additional code here if $success is false
        # For example:
        # Write-Host "Backup operation failed!"
        # Send-Notification -Message "Backup operation failed!"
    }
    
    if (-not $success) {
        # Log the failure
        $logFilePath = Join-Path -Path $logDir -ChildPath "failed.log"
        $logMessage = "Failed to copy and verify file: $file after $maxRetries attempts."
        Add-Content -Path $logFilePath -Value $logMessage
        Write-Error $logMessage
    }

    
    return $destinationPath
}
$fileInfos = @{}
function Get-FileInfo {
    # Read the file line by line
    foreach ($Line in $mainStorages) {
        $srcDir = $Line.src
        $dstDir = $Line.dst
        $logDir = ".\logs"
        $manifestFilePath = Process-Line -srcDir $srcDir

        if (Test-Path -Path $manifestFilePath -PathType Leaf) {
            Write-Host "The file exists: $manifestFilePath" -ForegroundColor Green
        }
        else {
            Write-Host "manifest file not found: $manifestFilePath. Creating new manifest..." -ForegroundColor Yellow
            # Create directory for logs if it doesn't exist
            if (!(Test-Path -Path .\logs -PathType Container)) {
                New-Item -ItemType Directory -Path .\logs
            }
            # Initialize a hashtable to hold file info
            $fileInfos = @{}
            
            # Get all files in the drive
            $files = Get-ChildItem -Path "$srcDir\" -Recurse -File
            foreach ($file in $files) {
                #Write-Host "Processing file: $file"
                $fileInfo = Get-FilesInfo -hashYN "Y" -file $file -Line $Line

                # Get the full path of the file
                $fullPath = (Get-Item $file).FullName
                
                # Modify the relative path to include the desired path structure
                $relativePath = $fullPath.Substring($srcDir.Length).TrimStart('\')
                
                # Create a new object excluding RelativePath
                $fileInfoWithoutRelativePath = $fileInfo | Select-Object -Property * -ExcludeProperty RelativePath
                
                # Add the item to the hashtable with the modified RelativePath as the key
                $fileInfos[$relativePath] = $fileInfoWithoutRelativePath

                # Call Add-Backup to move the file to the backup location
                Add-Backup -file $file -srcDir $srcDir -dstDir $dstDir -expectedHash $fileInfo.Hash -logDir $logDir
                ConvertTo-Json -Depth 10 -InputObject $fileInfos | Out-File -FilePath $manifestFilePath -Encoding utf8
            }
        }
    }
}

function Compare-Files {
    Get-FileInfo
    foreach ($Line in $mainStorages) {     
        $srcDir = $Line.src
        $dstDir = $Line.dst
        $manifestFilePath = Process-Line -srcDir $srcDir

        # Read the content of the hashtable from the file
        $infoFromFile = ConvertFrom-Json -InputObject (Get-Content -Path $manifestFilePath -Raw) -AsHashtable

        # Iterate through the hashtable to verify the structure
        foreach ($key in $infoFromFile.Keys) {
            $value = $infoFromFile[$key]
            #Write-Host "Key: $key"
        }

        # Initialize a hashtable to hold file info from disk
        $infoFromDisk = @{}  
        # Get all files in the drive
        #$files = Get-ChildItem -Path "$Line\" -Recurse -File
        foreach ($file in $files) {
            $fileInfo = Get-FilesInfo -hashYN "N" -file $file -Line $Line
            $relativePath = $fileInfo.RelativePath
            # Create a new object excluding RelativePath
            $fileInfoWithoutRelativePath = $fileInfo | Select-Object -Property * -ExcludeProperty RelativePath
            # Add the item to the hashtable with RelativePath as the key
            $infoFromDisk[$relativePath] = $fileInfoWithoutRelativePath
        }
        # Verify the content of the hashtable
        foreach ($key in $infoFromDisk.Keys) {
            $value = $infoFromDisk[$key]
            #Write-Host "Key Disk: $key"
        }
        # Compare the two hashtables
        foreach ($key in $infoFromDisk.Keys) {
            # Here is where I will add my logic to mark a file as deleted, added, or modified
            if ($infoFromFile.ContainsKey($key)) {
                #Write-Host "Checking file: $key"
                # Mark the file for deletion within the backup drive
                $fileToDelete = Join-Path -Path $Line -ChildPath $key
                Write-Host "Marking file for deletion: $fileToDelete"
                # Perform the deletion operation here
            }

        }
    }
}

$mainStorages = Import-Csv -Path .\config\main-storages.csv
Compare-Files