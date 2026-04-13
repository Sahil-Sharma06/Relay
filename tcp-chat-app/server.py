import socket
import threading
from datetime import datetime


HOST = "127.0.0.1"
PORT = 12345

clients_lock = threading.Lock()
clients = {}  # socket -> username


def timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def log_event(message: str) -> None:
    formatted = f"[{timestamp()}] {message}"
    print(formatted)
    with open("chat_log.txt", "a", encoding="utf-8") as log_file:
        log_file.write(formatted + "\n")


def remove_client(client_socket: socket.socket) -> None:
    with clients_lock:
        username = clients.pop(client_socket, None)

    if username:
        log_event(f"[SERVER] {username} disconnected")

    try:
        client_socket.close()
    except OSError:
        pass


def send_to_client(client_socket: socket.socket, message: str) -> bool:
    try:
        client_socket.sendall(message.encode("utf-8"))
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        remove_client(client_socket)
        return False


def broadcast(message: str, sender_socket: socket.socket) -> None:
    with clients_lock:
        recipients = [sock for sock in clients if sock is not sender_socket]

    for recipient in recipients:
        send_to_client(recipient, message)


def handle_client(client_socket: socket.socket, address: tuple[str, int]) -> None:
    username = ""

    try:
        # The first payload from a client is treated as their username.
        username_raw = client_socket.recv(1024)
        if not username_raw:
            remove_client(client_socket)
            return

        username = username_raw.decode("utf-8").strip() or f"User-{address[1]}"

        with clients_lock:
            clients[client_socket] = username

        log_event(f"[SERVER] {username} connected from {address[0]}:{address[1]}")
        broadcast(f"[{timestamp()}] [SERVER]: {username} joined the chat\n", client_socket)

        while True:
            data = client_socket.recv(4096)
            if not data:
                break

            message_text = data.decode("utf-8").strip()
            if not message_text:
                continue

            if message_text == "/list":
                with clients_lock:
                    users = ", ".join(sorted(clients.values()))
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Online users: {users}\n")
                continue

            if message_text == "/quit":
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Disconnecting...\n")
                break

            formatted = f"[{timestamp()}] [{username}]: {message_text}\n"
            log_event(formatted.rstrip())
            broadcast(formatted, client_socket)

    except (ConnectionResetError, BrokenPipeError, UnicodeDecodeError, OSError):
        pass
    finally:
        remove_client(client_socket)
        if username:
            broadcast(f"[{timestamp()}] [SERVER]: {username} left the chat\n", client_socket)


def start_server() -> None:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)

    print(f"Server listening on {HOST}:{PORT}")

    try:
        while True:
            client_socket, address = server_socket.accept()
            thread = threading.Thread(target=handle_client, args=(client_socket, address), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        with clients_lock:
            sockets_to_close = list(clients.keys())
            clients.clear()

        for sock in sockets_to_close:
            try:
                sock.close()
            except OSError:
                pass

        server_socket.close()


if __name__ == "__main__":
    start_server()