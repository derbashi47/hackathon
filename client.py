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

# Global order counter and lock
transfer_order = 1
transfer_order_lock = threading.Lock()

# Initialize colorama for colored logging
init(autoreset=True)

def log(message, level="info"):
    levels = {"info": Fore.GREEN, "warning": Fore.YELLOW, "error": Fore.RED}
    color = levels.get(level, Fore.WHITE)
    print(f"{color}[{time.strftime('%Y-%m-%d %H:%M:%S')}] [CLIENT] {message}{Style.RESET_ALL}")

def show_progress(current, total):
    bar_length = 30
    progress = int(bar_length * (current / total))
    bar = f"[{'#' * progress}{'.' * (bar_length - progress)}]"
    percentage = (current / total) * 100
    print(f"\r{bar} {percentage:.2f}% ({current}/{total} bytes)", end="", flush=True)

def listen_for_offers():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_socket.bind(('', UDP_BROADCAST_PORT))

    log("Listening for server offers...", "info")

    while True:
        ready, _, _ = select.select([udp_socket], [], [], 1)
        if udp_socket in ready:
            data, addr = udp_socket.recvfrom(1024)
            if len(data) >= 9:
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('!IBHH', data[:9])
                if magic_cookie == MAGIC_COOKIE and message_type == OFFER_TYPE:
                    log(f"Received offer from {addr[0]} (UDP: {udp_port}, TCP: {tcp_port})", "info")
                    return addr[0], tcp_port, udp_port

def tcp_download(server_ip, tcp_port, file_size):
    global transfer_order
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.connect((server_ip, tcp_port))
            tcp_socket.settimeout(5)

            # Send request message
            request_message = struct.pack('!IBQ', MAGIC_COOKIE, REQUEST_TYPE, file_size)
            tcp_socket.sendall(request_message)

            # Measure download time
            start_time = time.time()
            total_bytes = 0

            while total_bytes < file_size:
                try:
                    data = tcp_socket.recv(1024)
                    if not data:
                        break
                    total_bytes += len(data)
                    show_progress(total_bytes, file_size)
                except socket.timeout:
                    log("Timeout while receiving TCP packets. Retrying...", "warning")
                    continue

            elapsed_time = time.time() - start_time
            speed = total_bytes * 8 / elapsed_time if elapsed_time > 0 else 0
            success_rate = total_bytes / file_size * 100 if file_size > 0 else 0

            with transfer_order_lock:
                current_order = transfer_order
                transfer_order += 1

            log(f"\nTCP transfer #{current_order} finished: {total_bytes} bytes, time: {elapsed_time:.2f}s, speed: {speed:.2f} bps, success rate: {success_rate:.2f}%", "info")
    except Exception as e:
        log(f"Error during TCP download: {e}", "error")

def udp_download(server_ip, udp_port, file_size):
    global transfer_order
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.settimeout(5)

            # Send request message
            request_message = struct.pack('!IBQ', MAGIC_COOKIE, REQUEST_TYPE, file_size)
            udp_socket.sendto(request_message, (server_ip, udp_port))

            # Measure download time
            start_time = time.time()
            total_bytes = 0
            packets_received = set()
            packets_expected = file_size // 1024 + (1 if file_size % 1024 else 0)

            log("Starting UDP transfer...\n")

            while len(packets_received) < packets_expected:
                try:
                    data, _ = udp_socket.recvfrom(2048)
                    if len(data) >= 20:
                        magic_cookie, message_type, current_segment, total_segments = struct.unpack('!IBQQ', data[:21])

                        if magic_cookie == MAGIC_COOKIE and message_type == PAYLOAD_TYPE:
                            if current_segment not in packets_received:
                                packets_received.add(current_segment)
                                total_bytes += len(data) - 20
                                show_progress(len(packets_received), total_segments)
                except socket.timeout:
                    log("Timeout while waiting for UDP packets. Retrying...", "warning")
                    break

            elapsed_time = time.time() - start_time
            speed = total_bytes * 8 / elapsed_time if elapsed_time > 0 else 0
            success_rate = len(packets_received) / packets_expected * 100 if packets_expected > 0 else 0

            with transfer_order_lock:
                current_order = transfer_order
                transfer_order += 1

            log(f"\nUDP transfer #{current_order} finished: {total_bytes} bytes, time: {elapsed_time:.2f}s, speed: {speed:.2f} bps, success rate: {success_rate:.2f}%\n", "info")
    except Exception as e:
        log(f"Error during UDP download: {e}", "error")

def main():
    log("Client started.\n", "info")
    while True:
        server_ip, tcp_port, udp_port = listen_for_offers()

        try:
            file_size = int(input("Enter file size to download (in bytes): \n"))
            if file_size <= 0:
                raise ValueError("File size must be greater than 0.")

            # Start TCP and UDP transfers
            tcp_thread = threading.Thread(target=tcp_download, args=(server_ip, tcp_port, file_size), daemon=True)
            udp_thread = threading.Thread(target=udp_download, args=(server_ip, udp_port, file_size), daemon=True)

            tcp_thread.start()
            udp_thread.start()

            tcp_thread.join()
            udp_thread.join()

            log("All transfers complete. Listening for server offers again...\n", "info")
        except ValueError as e:
            log(f"Invalid input: {e}\n", "error")
        except Exception as e:
            log(f"Error in main loop: {e}\n", "error")

if __name__ == "__main__":
    main()
