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
# Global order counter and lock
transfer_order = 1
transfer_order_lock = threading.Lock()
# Helper function for logging
def log(message):
    print(f"[CLIENT] {message}")


# Function to listen for server offers
def listen_for_offers():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.bind(('', UDP_BROADCAST_PORT))

    #log("Listening for offers...")

    while True:

        ready, _, _ = select.select([udp_socket], [], [], 1)
        if udp_socket in ready:
            data, addr = udp_socket.recvfrom(1024)
            if len(data) >= 9:
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('!IBHH', data[:9])
                if magic_cookie == MAGIC_COOKIE and message_type == OFFER_TYPE:
                    log(f"Received offer from {addr[0]}")
                    return addr[0], tcp_port, udp_port


# Function to handle TCP
def tcp_download(server_ip, tcp_port, file_size):
    global transfer_order
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.connect((server_ip, tcp_port))

            # Send request message
            request_message = struct.pack('!IBQ', MAGIC_COOKIE, REQUEST_TYPE, file_size)
            tcp_socket.sendall(request_message)

            # Measure download time
            start_time = time.time()
            total_bytes = 0

            while total_bytes < file_size:
                ready, _, _ = select.select([tcp_socket], [], [], 1)
                if tcp_socket in ready:
                    data = tcp_socket.recv(1024)
                    if not data:
                        break
                    total_bytes += len(data)

            elapsed_time = time.time() - start_time
            speed = total_bytes * 8 / elapsed_time
            with transfer_order_lock:
                current_order = transfer_order
                transfer_order += 1
            log(f"TCP transfer #{current_order} finished: {total_bytes} bytes, time: {elapsed_time:.2f}s, speed: {speed:.2f} bps")
    except Exception as e:
        log(f"Error during TCP download: {e}")


# Function to handle UDP download
def udp_download(server_ip, udp_port, file_size):
    global transfer_order
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.settimeout(1)

            # Send request message
            request_message = struct.pack('!IBQ', MAGIC_COOKIE, REQUEST_TYPE, file_size)
            udp_socket.sendto(request_message, (server_ip, udp_port))

            # Measure download time
            start_time = time.time()
            total_bytes = 0
            packets_received = 0
            packets_expected = 0
            total_segments = 0

            while True:
                try:
                    data, _ = udp_socket.recvfrom(2048)
                    #log(f"Received packet of size {len(data)} bytes.")
                    if len(data) >= 20:  # Ensure the packet is large enough
                        magic_cookie, message_type, current_segment, total_segments = struct.unpack('!IBQQ', data[:21])
                        if magic_cookie == MAGIC_COOKIE and message_type == PAYLOAD_TYPE:
                            packets_received += 1
                            packets_expected = total_segments
                            total_bytes += len(data) - 20
                    else:
                        log(f"Received an incomplete packet of size {len(data)} bytes.")
                except socket.timeout:
                    break

            elapsed_time = time.time() - start_time
            speed = total_bytes * 8 / elapsed_time if elapsed_time > 0 else 0
            packet_loss = (1 - (packets_received / packets_expected)) * 100 if packets_expected > 0 else 100
            percentage_received = (packets_received / total_segments) * 100 if total_segments > 0 else 0
            with transfer_order_lock:
                current_order = transfer_order
                transfer_order += 1
            log(f"UDP transfer #{current_order} finished, {total_bytes} bytes, Total time: {elapsed_time:.2f}s, Total speed: {speed:.2f} bps, packets received: {packets_received:.2f}%")

    except Exception as e:
        log(f"Error during UDP download: {e}")

# Main client function
def main():
    log("Client started, listening for offer requests...")
    while True:
        server_ip, tcp_port, udp_port = listen_for_offers()

        try:
            file_size = int(input("Enter file size to download (in bytes): "))

            # Start TCP and UDP transfers
            tcp_thread = threading.Thread(target=tcp_download, args=(server_ip, tcp_port, file_size), daemon=True)
            udp_thread = threading.Thread(target=udp_download, args=(server_ip, udp_port, file_size), daemon=True)

            tcp_thread.start()
            udp_thread.start()

            tcp_thread.join()
            udp_thread.join()

            log("All transfers complete. listening for offer requests")
        except Exception as e:
            log(f"Error in main client loop: {e}")


if __name__ == "__main__":
    main()