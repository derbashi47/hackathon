import socket
import threading
import struct
import time
import select

MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4
UDP_BROADCAST_PORT = 13117
TCP_PORT = 65432

def log(message):
    print(f"[SERVER] {message}")

def broadcast_offers():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    offer_message = struct.pack('!IBHH', MAGIC_COOKIE, OFFER_TYPE, UDP_BROADCAST_PORT, TCP_PORT)

    while True:
        udp_socket.sendto(offer_message, ('<broadcast>', UDP_BROADCAST_PORT))
        log("Broadcasted offer packet.")
        time.sleep(1)

def handle_client(client_socket, client_address):
    try:
        data = client_socket.recv(1024)
        if len(data) < 13:
            log(f"Invalid request from {client_address}.")
            return

        magic_cookie, message_type, file_size = struct.unpack('!IBQ', data[:13])
        if magic_cookie != MAGIC_COOKIE or message_type != REQUEST_TYPE:
            log(f"Invalid request format from {client_address}.")
            return

        log(f"Received valid request from {client_address}, file size: {file_size} bytes.")

        payload = b'A' * 1024  # 1 KB chunk
        bytes_sent = 0

        while bytes_sent < file_size:
            ready, _, _ = select.select([], [client_socket], [], 1)
            if client_socket in ready:
                client_socket.send(payload)
                bytes_sent += len(payload)

        log(f"Completed TCP transfer to {client_address}, total bytes: {bytes_sent}.")
    except Exception as e:
        log(f"Error handling client {client_address}: {e}")
    finally:
        client_socket.close()

def tcp_server():
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.bind(("", TCP_PORT))
    tcp_socket.listen(5)
    log(f"TCP server listening on port {TCP_PORT}.")

    while True:
        client_socket, client_address = tcp_socket.accept()
        log(f"Accepted connection from {client_address}.")
        threading.Thread(target=handle_client, args=(client_socket, client_address), daemon=True).start()

def handle_udp_request(data, client_address, udp_socket):
    try:
        if len(data) < 13:
            log(f"Invalid UDP request from {client_address}.")
            return

        magic_cookie, message_type, file_size = struct.unpack('!IBQ', data[:13])
        if magic_cookie != MAGIC_COOKIE or message_type != REQUEST_TYPE:
            log(f"Invalid UDP request format from {client_address}.")
            return

        log(f"Valid UDP request from {client_address}, file size: {file_size} bytes.")

        segment_count = 0
        payload = b'A' * 1024  # 1 KB chunk

        while segment_count * len(payload) < file_size:
            segment_count += 1
            payload_message = struct.pack('!IBQQ', MAGIC_COOKIE, PAYLOAD_TYPE, segment_count, file_size) + payload
            udp_socket.sendto(payload_message, client_address)

        log(f"Completed UDP transfer to {client_address}, total segments: {segment_count}.")
    except Exception as e:
        log(f"Error handling UDP request from {client_address}: {e}")

def udp_server():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(("", UDP_BROADCAST_PORT))
    log(f"UDP server listening on port {UDP_BROADCAST_PORT}.")

    while True:
        ready, _, _ = select.select([udp_socket], [], [], 1)
        if udp_socket in ready:
            data, client_address = udp_socket.recvfrom(1024)
            threading.Thread(target=handle_udp_request, args=(data, client_address, udp_socket), daemon=True).start()

def main():
    log("Starting server...")

    threading.Thread(target=broadcast_offers, daemon=True).start()
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=udp_server, daemon=True).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
