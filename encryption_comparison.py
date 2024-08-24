import hashlib
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from base64 import b64encode, b64decode
import json
import time
import os
import csv

def encrypt_with_aes_gcm(plaintext, key, output_file):
    cipher = AES.new(key, AES.MODE_GCM)
    cipher.update(b"header")
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    result = json.dumps({
        'nonce': b64encode(cipher.nonce).decode('utf-8'),
        'header': b64encode(b"header").decode('utf-8'),
        'ciphertext': b64encode(ciphertext).decode('utf-8'),
        'tag': b64encode(tag).decode('utf-8')
    })

    with open(output_file, 'w') as f:
        f.write(result)

    return result

def decrypt_with_aes_gcm(input_file, key):
    with open(input_file, 'r') as f:
        data = json.load(f)

    nonce = b64decode(data['nonce'])
    header = b64decode(data['header'])
    ciphertext = b64decode(data['ciphertext'])
    tag = b64decode(data['tag'])

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(header)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)

    return plaintext

def run_tests(plaintext, key_size, iterations=10):
    results = []

    for _ in range(iterations):
        salt = get_random_bytes(16)
        key = hashlib.pbkdf2_hmac('sha256', b'ThisIsSecretKey', salt, 10, dklen=key_size // 8)
        if len(key) not in [16, 24, 32]:
            raise ValueError(f"Incorrect AES key length ({len(key)} bytes)")
        encrypted_file = f'A:\\test\\Vid\\homevid(1)_aes{key_size}.enc'

        start_time = time.time()
        encrypt_with_aes_gcm(plaintext, key, encrypted_file)
        encryption_time = time.time() - start_time

        start_time = time.time()
        decrypted_text = decrypt_with_aes_gcm(encrypted_file, key)
        decryption_time = time.time() - start_time

        assert plaintext == decrypted_text, f"AES-{key_size}-GCM decryption failed"

        results.append((key_size, encryption_time, decryption_time))

    return results

def save_results_to_csv(results, csv_file):
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Key Size', 'Encryption Time (s)', 'Decryption Time (s)'])
        writer.writerows(results)

def main():
    file_path = 'A:\\test\\Vid\\homevid(1).mkv'
    with open(file_path, 'rb') as f:
        plaintext = f.read()

    all_results = []
    for key_size in [128, 192, 256]:
        results = run_tests(plaintext, key_size)
        all_results.extend(results)

    save_results_to_csv(all_results, 'encryption_decryption_times.csv')
    print("AES-GCM Encryption and Decryption tests completed successfully")

if __name__ == "__main__":
    main()