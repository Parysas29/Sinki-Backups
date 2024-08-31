Welcome to Sinki-Backups.
I started development on this project out of a need for a secure method to backup my files to offsite locations without fearing that unauthorized parties would not gain access to my personal data.
##This script performs the following operations
### Pre-Operations
To bring files from off site locations like Google Drive or OneDrive into the backup process I have created my own custom wrapper around rclone to handle it operations for moving files to and from offsite locations.
### Main Process
The main process so far involves taking all of the files in the source directory and copying it to the backup directory while performing the following operations.
Compress, Split (if over 4gb), encrypt, hashing
*Compression: * right now all files over 120 bytes are being compressed into XZ format this allow crc64 hash to be embedded into the compressed file to help ensure file integrity, additionally files over 1GB in size will be uncompressed into memory to ensure that data didn’t get corrupted during the compression process.
*Split: * As the plan is to prepare these files for offsite storage, I find it useful to have the files be split so that if the network connection become interrupted while transferring a large file the entire file won’t need to be retransferred to the offsite location.
* Encryption: * For the encryption method I am employing AES-128-GCM encryption for it ability to verify the file upon dencryption.
* Hashing: * While throughout the processing of these files I do use md5sum hashes internally I personally find md5 to be a perfectly fine hashing method within a controlled and known environment however once the file have been fully processed and ready to be transferred to an offsite location that where I will be employing sha256sum hashing as that the minimal standard I like to use while downloading files from untrusted locations.
### Post-Operations
This will involve the transferring of files to offsite locations, which this operation will be employed once again by using rclone for the transferring of these files.
## Restoring files
Of course, what is a backup solution without the ability to restore files which is why if we want to restore files, we just need to do those operations in reverse.

Right now, as there are still a lot of unknown for me in software development, I feel uncomfortable assigning version numbers for each version of the code base I am working on now. However once both the backup code and restore code are working completely, and I have an interface so that people can interact with I plan on assigning that as version 1.0.

While I still have a lot of unknown for version 2.0 and my current plans are subjective to change, I currently am planning/thinking about doing the following
1.	Improve the code to follow best programming practices
2.	Add more customization to allow people to choose the following settings
a.	Files extensions not to compress
b.	What size we split files at if any
c.	Encryption method
d.	Bandwidth setting for rclone
e.	Setting the time in millisecond for pbkdf2 optimal iteration with option to disable it completely.
3.	Running all operations in ram before final copy onto the local backup drive.
4.	Running a program that don’t use rclone in parallel. (Will be using rclone parallel feature for operations that depend on rclone.
