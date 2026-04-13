import argparse
import socket
import threading
from collections import deque
from datetime import datetime


HOST = "127.0.0.1"
PORT = 12345
BACKLOG = 5
MAX_HISTORY = 100

clients_lock = threading.Lock()
clients = {}  # socket -> username
history_lock = threading.Lock()
message_history = deque(maxlen=MAX_HISTORY)
stats_lock = threading.Lock()
total_messages = 0


def timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def log_event(message: str) -> None:
    formatted = f"[{timestamp()}] {message}"
    print(formatted)
    with open("chat_log.txt", "a", encoding="utf-8") as log_file:
        log_file.write(formatted + "\n")


def add_history(message: str) -> None:
    with history_lock:
        message_history.append(message.rstrip())


def increment_message_count() -> None:
    global total_messages
    with stats_lock:
        total_messages += 1


def get_message_count() -> int:
    with stats_lock:
        return total_messages


def username_in_use(username: str) -> bool:
    with clients_lock:
        return username in clients.values()


def get_unique_username(preferred: str, fallback_suffix: int) -> str:
    base = preferred.strip() or f"User-{fallback_suffix}"
    candidate = base
    counter = 1
    while username_in_use(candidate):
        candidate = f"{base}{counter}"
        counter += 1
    return candidate


def find_socket_by_username(username: str) -> socket.socket | None:
    with clients_lock:
        for sock, name in clients.items():
            if name == username:
                return sock
    return None


def get_usernames_snapshot() -> list[str]:
    with clients_lock:
        return sorted(clients.values())


def remove_client(client_socket: socket.socket) -> str | None:
    with clients_lock:
        username = clients.pop(client_socket, None)

    if username:
        log_event(f"[SERVER] {username} disconnected")

    try:
        client_socket.close()
    except OSError:
        pass

    return username


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


def send_help(client_socket: socket.socket) -> None:
    help_text = (
        f"[{timestamp()}] [SERVER]: Available commands:\n"
        "  /help                  Show this command list\n"
        "  /list                  Show online users\n"
        "  /dm <user> <message>   Send a private message\n"
        "  /rename <new_name>     Change your display name\n"
        "  /history [n]           Show the last n messages (default 20)\n"
        "  /stats                 Show server chat stats\n"
        "  /quit                  Disconnect cleanly\n"
    )
    send_to_client(client_socket, help_text)


def handle_command(client_socket: socket.socket, username: str, command_line: str) -> tuple[bool, str]:
    parts = command_line.split(" ", 2)
    command = parts[0].lower()

    if command == "/help":
        send_help(client_socket)
        return False, username

    if command == "/list":
        users = ", ".join(get_usernames_snapshot())
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Online users: {users}\n")
        return False, username

    if command == "/history":
        count = 20
        if len(parts) >= 2 and parts[1].strip():
            try:
                count = int(parts[1].strip())
            except ValueError:
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Usage: /history [n]\n")
                return False, username

        count = max(1, min(MAX_HISTORY, count))
        with history_lock:
            snapshot = list(message_history)[-count:]

        if not snapshot:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: No chat history yet.\n")
            return False, username

        payload = "\n".join(snapshot)
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Last {len(snapshot)} messages:\n{payload}\n")
        return False, username

    if command == "/stats":
        users_online = len(get_usernames_snapshot())
        messages_sent = get_message_count()
        send_to_client(
            client_socket,
            f"[{timestamp()}] [SERVER]: Users online: {users_online}, total chat messages: {messages_sent}\n",
        )
        return False, username

    if command == "/dm":
        if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Usage: /dm <user> <message>\n")
            return False, username

        target_name = parts[1].strip()
        dm_text = parts[2].strip()
        target_socket = find_socket_by_username(target_name)

        if target_socket is None:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: User '{target_name}' is not online.\n")
            return False, username

        if target_socket is client_socket:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You cannot DM yourself.\n")
            return False, username

        outbound = f"[{timestamp()}] [DM from {username}]: {dm_text}\n"
        if send_to_client(target_socket, outbound):
            send_to_client(client_socket, f"[{timestamp()}] [DM to {target_name}]: {dm_text}\n")
            log_event(f"[DM] {username} -> {target_name}: {dm_text}")
        return False, username

    if command == "/rename":
        if len(parts) < 2 or not parts[1].strip():
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Usage: /rename <new_name>\n")
            return False, username

        new_name = parts[1].strip()
        if new_name == username:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You are already using that name.\n")
            return False, username

        if username_in_use(new_name):
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Username '{new_name}' is already taken.\n")
            return False, username

        with clients_lock:
            if client_socket in clients:
                clients[client_socket] = new_name

        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You are now known as {new_name}.\n")
        broadcast(f"[{timestamp()}] [SERVER]: {username} is now known as {new_name}\n", client_socket)
        log_event(f"[SERVER] {username} renamed to {new_name}")
        return False, new_name

    if command == "/quit":
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Disconnecting...\n")
        return True, username

    send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Unknown command. Try /help\n")
    return False, username


def handle_client(client_socket: socket.socket, address: tuple[str, int]) -> None:
    username = ""

    try:
        # The first payload from a client is treated as their username.
        username_raw = client_socket.recv(1024)
        if not username_raw:
            remove_client(client_socket)
            return

        requested_name = username_raw.decode("utf-8").strip()
        username = get_unique_username(requested_name, address[1])

        with clients_lock:
            clients[client_socket] = username

        log_event(f"[SERVER] {username} connected from {address[0]}:{address[1]}")
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Welcome, {username}! Type /help for commands.\n")
        broadcast(f"[{timestamp()}] [SERVER]: {username} joined the chat\n", client_socket)

        while True:
            data = client_socket.recv(4096)
            if not data:
                break

            message_text = data.decode("utf-8").strip()
            if not message_text:
                continue

            if message_text.startswith("/"):
                should_disconnect, username = handle_command(client_socket, username, message_text)
                if should_disconnect:
                    break
                continue

            formatted = f"[{timestamp()}] [{username}]: {message_text}\n"
            log_event(formatted.rstrip())
            add_history(formatted)
            increment_message_count()
            broadcast(formatted, client_socket)

    except (ConnectionResetError, BrokenPipeError, UnicodeDecodeError, OSError):
        pass
    finally:
        removed_user = remove_client(client_socket)
        if removed_user:
            broadcast(f"[{timestamp()}] [SERVER]: {removed_user} left the chat\n", client_socket)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-client TCP chat server")
    parser.add_argument("--host", default=HOST, help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT, help="Port to listen on (default: 12345)")
    parser.add_argument("--backlog", type=int, default=BACKLOG, help="Listen backlog (default: 5)")
    return parser.parse_args()


def start_server(host: str, port: int, backlog: int) -> None:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(max(5, backlog))

    print(f"Server listening on {host}:{port}")

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
    args = parse_args()
    start_server(args.host, args.port, args.backlog)