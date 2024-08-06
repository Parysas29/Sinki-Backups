package main

import (
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Operation struct {
	Type      string
	SourceDir string
	DestDir   string
}

type Storage struct {
	Src string
	Dst string
}

type FileInfo struct {
	RelativePath string    `json:"relative_path"`
	Size         int64     `json:"size"`
	ModTime      time.Time `json:"mod_time"`
	Hash         string    `json:"hash"`
}

func PreOperations() {
	// open file
	f, err := os.Open("./config/pre-operations.csv")
	if err != nil {
		log.Fatal(err)
	}
	// remember to close the file at the end of the program
	defer f.Close()

	// read csv values using csv.Reader
	csvReader := csv.NewReader(f)

	// Skip the header if there is one
	if _, err := csvReader.Read(); err != nil {
		log.Fatal("Error reading CSV header:", err)
	}

	// Define common arguments for rclone sync operations
	commonSyncArgs := []string{"--bwlimit=20M:2G", "--fast-list", "--multi-thread-streams=10", "--delete-during", "-P"}

	for {
		// read each record from csv
		record, err := csvReader.Read()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			log.Println("Error reading CSV record:", err)
			continue
		}

		// create operation
		op := Operation{
			Type:      record[0],
			SourceDir: record[1],
			DestDir:   record[2],
		}
		log.Println(op)

		// Construct command arguments dynamically
		var args []string
		switch op.Type {
		case "rclone-dedupe":
			args = append(args, "dedupe", "rename")
			if op.DestDir != "" {
				args = append(args, op.DestDir)
			}
		case "rclone-sync-google":
			args = append(args, "sync", "--drive-acknowledge-abuse")
			args = append(args, commonSyncArgs...)
			fmt.Println("this is the variable args:", args)
			if op.SourceDir != "" {
				args = append(args, op.SourceDir)
			}
			if op.DestDir != "" {
				args = append(args, op.DestDir)
			}
			fmt.Println("this is the variable args:", args)
		case "rclone-sync-onedrive":
			args = append(args, "sync", "--onedrive-delta")
			args = append(args, commonSyncArgs...)
			if op.SourceDir != "" {
				args = append(args, op.SourceDir)
			}
			if op.DestDir != "" {
				args = append(args, op.DestDir)
			}
		default:
			log.Printf("Unknown operation: %s", op.Type)
			continue
		}

		// Print the args variable and the message
		fmt.Println("this is the variable args:", args)

		// Execute the command
		cmd := exec.Command("rclone", args...)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr

		log.Printf("Executing: %s", cmd.String())
		if err := cmd.Run(); err != nil {
			log.Printf("Error executing command: %v", err)
		}
	}
}

func GetFilesInfo(hashYN string, file string, line string) (FileInfo, error) {
	var hash string
	if hashYN == "Y" {
		data, err := os.ReadFile(file)
		if err != nil {
			return FileInfo{}, err
		}
		hashBytes := sha256.Sum256(data)
		hash = hex.EncodeToString(hashBytes[:])
	}

	relativePath := strings.TrimPrefix(file, line)
	fileInfo, err := os.Stat(file)
	if err != nil {
		return FileInfo{}, err
	}

	return FileInfo{
		Hash:         hash,
		RelativePath: relativePath,
		ModTime:      fileInfo.ModTime(),
		Size:         fileInfo.Size(),
	}, nil
}

func ProcessLine(srcDir string) string {
	manifest := fmt.Sprintf("%s%s.manifest", srcDir[:1], filepath.Base(srcDir))
	manifest = strings.ReplaceAll(manifest, " ", "_")
	fmt.Println("Manifest:", manifest)
	manifestFilePath := filepath.Join(".", "logs", manifest)
	return manifestFilePath
}

func AddBackup(file, srcDir, dstDir, expectedHash, logDir string) (string, error) {
	// Check if the path is a file
	fileInfo, err := os.Stat(file)
	if err != nil || fileInfo.IsDir() {
		fmt.Println("Skipping directory:", file)
		return "", nil
	}

	// Get the full path of the file
	fullPath, err := filepath.Abs(file)
	if err != nil {
		return "", err
	}

	// Calculate the relative path
	relativePath := strings.TrimPrefix(fullPath, srcDir)
	relativePath = strings.TrimPrefix(relativePath, string(os.PathSeparator))

	// Construct the destination path with the relative path
	destinationPath := filepath.Join(dstDir, relativePath)

	// Ensure the destination directory exists
	destinationDir := filepath.Dir(destinationPath)
	if _, err := os.Stat(destinationDir); os.IsNotExist(err) {
		err = os.MkdirAll(destinationDir, os.ModePerm)
		if err != nil {
			return "", err
		}
	}

	maxRetries := 3
	attempt := 0
	success := false

	for attempt < maxRetries && !success {
		// Copy the file to the backup location
		err = copyFile(fullPath, destinationPath)
		if err != nil {
			return "", err
		}

		// Verify the hash sum of the copied file
		copiedFileHash, err := getFileHash(destinationPath)
		if err != nil {
			return "", err
		}

		if copiedFileHash == expectedHash {
			fmt.Println("File copied and verified successfully:", file)
			time.Sleep(25 * time.Millisecond)

			// Compress the file using 7zip
			compressedFilePath := destinationPath + ".7z"
			cmd := exec.Command("7z", "a", "-t7z", "-m0=lzma2", "-mx=9", "-mfb=64", "-md=32m", "-ms=on", compressedFilePath, destinationPath)
			fmt.Println("Compressing file:", file)
			err = cmd.Run()
			if err != nil {
				return "", err
			}
			success = true
		} else {
			fmt.Printf("Hash mismatch for file: %s. Attempt %d of %d.\n", file, attempt+1, maxRetries)
			attempt++
		}
	}

	if !success {
		// Log the failure
		logFilePath := filepath.Join(logDir, "failed.log")
		logMessage := fmt.Sprintf("Failed to copy and verify file: %s after %d attempts.", file, maxRetries)
		err = appendToFile(logFilePath, logMessage)
		if err != nil {
			return "", err
		}
		fmt.Println(logMessage)
		return "", fmt.Errorf(logMessage)
	}

	return destinationPath, nil
}

func GatherFileInfo(mainStorage []Storage) {
	if len(mainStorage) == 0 {
		fmt.Println("No data to process")
		return
	}

	fmt.Println("This is me", mainStorage)

	for _, storage := range mainStorage[1:] {
		src := storage.Src
		dst := storage.Dst
		fmt.Println("Source inside GatherFileInfo", src)
		fmt.Println("Destination inside GatherFileInfo", dst)

		base := filepath.Base(src)
		manifestFileName := base + ".manifest"
		manifestFilePath := filepath.Join("./logs", manifestFileName)

		if _, err := os.Stat(manifestFilePath); os.IsNotExist(err) {
			fmt.Printf("Manifest file does not exist: %s\n", manifestFilePath)
			// Create the manifest file
			fmt.Printf("Manifest file created: %s\n", manifestFilePath)
		} else {
			fmt.Printf("Manifest file exists: %s\n", manifestFilePath)
		}
	}
}

func getFileHash(filePath string) (string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return "", err
	}
	defer file.Close()

	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}

	return hex.EncodeToString(hash.Sum(nil)), nil
}

func appendToFile(filePath, text string) error {
	f, err := os.OpenFile(filePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = f.WriteString(text + "\n")
	return err
}

// copyFile copies a file from src to dst. If dst does not exist, it is created.
func copyFile(src, dst string) error {
	// Open the source file
	sourceFile, err := os.Open(src)
	if err != nil {
		return err
	}
	defer sourceFile.Close()

	// Create the destination file
	destinationFile, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer destinationFile.Close()

	// Copy the contents from source to destination
	_, err = io.Copy(destinationFile, sourceFile)
	if err != nil {
		return err
	}

	// Flush the contents to disk
	err = destinationFile.Sync()
	if err != nil {
		return err
	}

	return nil
}

func readCSV(filePath string) ([]Storage, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}

	var storages []Storage
	for _, record := range records {
		storages = append(storages, Storage{
			Src: record[0],
			Dst: record[1],
		})
	}

	return storages, nil
}

func main() {
	filePath := "./config/main-storages.csv"
	mainStorage, err := readCSV(filePath)
	if err != nil {
		log.Fatalf("Error reading CSV file: %v", err)
	}
	//fmt.Print("mainStorage var in main", mainStorage)
	GatherFileInfo(mainStorage)

	for _, mainStorages := range mainStorage {
		log.Printf("Src: %s, Dst: %s", mainStorages.Src, mainStorages.Dst)
	}

}
