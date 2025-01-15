import socket
import threading
import struct
import time
import select
from colorama import init, Fore, Style

MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4
UDP_BROADCAST_PORT = 13117
TCP_PORT = 65432

init(autoreset=True)

def log(message, level="info"):
    levels = {"info": Fore.GREEN, "warning": Fore.YELLOW, "error": Fore.RED}
    color = levels.get(level, Fore.WHITE)
    print(f"{color}[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SERVER] {message}{Style.RESET_ALL}")

def get_server_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        return f"Error determining server IP: {e}"

def broadcast_offers():
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        offer_message = struct.pack('!IBHH', MAGIC_COOKIE, OFFER_TYPE, UDP_BROADCAST_PORT, TCP_PORT)

        log(f"Broadcasting offers on UDP port {UDP_BROADCAST_PORT}.")
        while True:
            udp_socket.sendto(offer_message, ('<broadcast>', UDP_BROADCAST_PORT))
            time.sleep(1)
    except Exception as e:
        log(f"Error broadcasting offers: {e}", "error")
        raise

def handle_tcp_client(client_socket, client_address):
    try:
        data = client_socket.recv(1024)
        if len(data) < 13:
            log(f"Invalid TCP request from {client_address}.", "warning")
            return

        magic_cookie, message_type, file_size = struct.unpack('!IBQ', data[:13])
        if magic_cookie != MAGIC_COOKIE or message_type != REQUEST_TYPE:
            log(f"Invalid TCP request format from {client_address}.", "warning")
            return

        log(f"Received valid TCP request from {client_address}, file size: {file_size} bytes.")

        payload = b'A' * 1024
        bytes_sent = 0

        while bytes_sent < file_size:
            remaining_bytes = file_size - bytes_sent
            chunk_size = min(1024, remaining_bytes)
            client_socket.sendall(payload[:chunk_size])
            bytes_sent += chunk_size

        log(f"Completed TCP transfer to {client_address}, total bytes: {bytes_sent}.")
    except Exception as e:
        log(f"Error handling TCP client {client_address}: {e}", "error")
    finally:
        client_socket.close()

def tcp_server():
    try:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.bind(("", TCP_PORT))
        tcp_socket.listen(10)
        log(f"TCP server listening on port {TCP_PORT}.")

        while True:
            try:
                client_socket, client_address = tcp_socket.accept()
                log(f"Accepted connection from {client_address}.")
                threading.Thread(target=handle_tcp_client, args=(client_socket, client_address), daemon=True).start()
            except socket.timeout:
                log("No TCP requests received recently.", "warning")
    except Exception as e:
        log(f"Error in TCP server: {e}", "error")
        raise

def handle_udp_request(data, client_address, udp_socket):
    try:
        if len(data) < 13:
            return

        magic_cookie, message_type, file_size = struct.unpack('!IBQ', data[:13])
        if magic_cookie != MAGIC_COOKIE or message_type != REQUEST_TYPE:
            log(f"Invalid UDP request format from {client_address}.", "warning")
            return

        log(f"Valid UDP request from {client_address}, file size: {file_size} bytes.")

        segment_count = 0
        payload = b'A' * 1024
        udp_socket.settimeout(2)

        while segment_count * len(payload) < file_size:
            try:
                segment_count += 1
                payload_message = struct.pack('!IBQQ', MAGIC_COOKIE, PAYLOAD_TYPE, segment_count, file_size) + payload
                udp_socket.sendto(payload_message, client_address)
            except socket.timeout:
                log(f"Timeout while sending packet {segment_count} to {client_address}. Retrying...", "warning")

        log(f"Completed UDP transfer to {client_address}, total segments: {segment_count}.")
    except Exception as e:
        log(f"Error handling UDP request from {client_address}: {e}", "error")

def udp_server():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(("", UDP_BROADCAST_PORT))
    udp_socket.settimeout(5)
    log(f"UDP server listening on port {UDP_BROADCAST_PORT}.")

    while True:
        try:
            ready, _, _ = select.select([udp_socket], [], [], 1)
            if udp_socket in ready:
                data, client_address = udp_socket.recvfrom(1024)
                threading.Thread(target=handle_udp_request, args=(data, client_address, udp_socket), daemon=True).start()
        except socket.timeout:
            log("No UDP requests received recently.", "warning")

def main():
    log(f"Server started, listening on IP address {get_server_ip()}")

    threading.Thread(target=broadcast_offers, daemon=True).start()
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=udp_server, daemon=True).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
