package main

import (
	"encoding/csv"
	"errors"
	"io"
	"log"
	"os"
	"os/exec"
)

type Operation struct {
	Type      string
	SourceDir string
	DestDir   string
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
			if op.SourceDir != "" {
				args = append(args, op.SourceDir)
			}
			if op.DestDir != "" {
				args = append(args, op.DestDir)
			}
		case "rclone-sync-onedrive":
			args = append(args, "sync", "--onedrive-delta")
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

func main() {
	PreOperations()
}
