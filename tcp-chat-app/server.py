import argparse
import socket
import threading
from collections import deque
from datetime import datetime
from time import monotonic


HOST = "127.0.0.1"
PORT = 12345
BACKLOG = 5
MAX_HISTORY = 100
DEFAULT_ROOM = "lobby"
RATE_WINDOW_SECONDS = 5
RATE_MAX_MESSAGES = 8

clients_lock = threading.Lock()
clients = {}  # socket -> username
rooms_lock = threading.Lock()
client_rooms = {}  # socket -> room
history_lock = threading.Lock()
message_history = deque(maxlen=MAX_HISTORY)
stats_lock = threading.Lock()
total_messages = 0
message_id_lock = threading.Lock()
next_id = 1
rate_lock = threading.Lock()
rate_timestamps = {}  # socket -> deque[float]
moderation_lock = threading.Lock()
muted_until = {}  # socket -> monotonic timestamp
banned_usernames = set()
ADMIN_USERS = {"admin"}


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


def get_next_message_id() -> int:
    global next_id
    with message_id_lock:
        current = next_id
        next_id += 1
    return current


def increment_message_count() -> None:
    global total_messages
    with stats_lock:
        total_messages += 1


def get_message_count() -> int:
    with stats_lock:
        return total_messages


def get_client_room(client_socket: socket.socket) -> str:
    with rooms_lock:
        return client_rooms.get(client_socket, DEFAULT_ROOM)


def set_client_room(client_socket: socket.socket, room: str) -> None:
    with rooms_lock:
        client_rooms[client_socket] = room


def get_rooms_snapshot() -> dict[str, int]:
    with rooms_lock:
        counts = {}
        for room in client_rooms.values():
            counts[room] = counts.get(room, 0) + 1
    return counts


def is_rate_limited(client_socket: socket.socket) -> bool:
    now = monotonic()
    with rate_lock:
        bucket = rate_timestamps.setdefault(client_socket, deque())
        while bucket and now - bucket[0] > RATE_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_MAX_MESSAGES:
            return True

        bucket.append(now)
        return False


def is_muted(client_socket: socket.socket) -> bool:
    now = monotonic()
    with moderation_lock:
        until = muted_until.get(client_socket)
        if until is None:
            return False
        if now >= until:
            muted_until.pop(client_socket, None)
            return False
        return True


def is_admin(username: str) -> bool:
    return username.lower() in {name.lower() for name in ADMIN_USERS}


def username_in_use(username: str) -> bool:
    with clients_lock:
        return username in clients.values()


def is_username_banned(username: str) -> bool:
    with moderation_lock:
        return username.lower() in banned_usernames


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


def get_users_with_rooms() -> list[str]:
    with clients_lock, rooms_lock:
        users = [f"{name}@{client_rooms.get(sock, DEFAULT_ROOM)}" for sock, name in clients.items()]
    return sorted(users)


def remove_client(client_socket: socket.socket) -> str | None:
    with clients_lock:
        username = clients.pop(client_socket, None)

    with rooms_lock:
        client_rooms.pop(client_socket, None)

    with rate_lock:
        rate_timestamps.pop(client_socket, None)

    with moderation_lock:
        muted_until.pop(client_socket, None)

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


def broadcast(
    message: str,
    sender_socket: socket.socket,
    room: str | None = None,
    include_sender: bool = False,
) -> int:
    with clients_lock, rooms_lock:
        recipients = []
        for sock in clients:
            if not include_sender and sock is sender_socket:
                continue
            if room is not None and client_rooms.get(sock, DEFAULT_ROOM) != room:
                continue
            recipients.append(sock)

    delivered = 0
    for recipient in recipients:
        if send_to_client(recipient, message):
            delivered += 1
    return delivered


def send_help(client_socket: socket.socket) -> None:
    help_text = (
        f"[{timestamp()}] [SERVER]: Available commands:\n"
        "  /help                  Show this command list\n"
        "  /list                  Show online users with their rooms\n"
        "  /rooms                 Show active rooms\n"
        "  /where                 Show your current room\n"
        "  /join <room>           Join a room\n"
        "  /leave                 Return to lobby\n"
        "  /dm <user> <message>   Send a private message\n"
        "  /rename <new_name>     Change your display name\n"
        "  /history [n]           Show the last n messages (default 20)\n"
        "  /stats                 Show server chat stats\n"
        "  /kick <user>           (admin) Disconnect a user\n"
        "  /mute <user> <secs>    (admin) Temporarily mute a user\n"
        "  /ban <user>            (admin) Ban username and disconnect user\n"
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
        users = ", ".join(get_users_with_rooms())
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Online users: {users}\n")
        return False, username

    if command == "/rooms":
        rooms = get_rooms_snapshot()
        if not rooms:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: No active rooms.\n")
            return False, username
        payload = ", ".join([f"{room}({count})" for room, count in sorted(rooms.items())])
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Active rooms: {payload}\n")
        return False, username

    if command == "/where":
        current_room = get_client_room(client_socket)
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You are in room '{current_room}'.\n")
        return False, username

    if command == "/join":
        if len(parts) < 2 or not parts[1].strip():
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Usage: /join <room>\n")
            return False, username

        new_room = parts[1].strip().lower()
        if not new_room.isalnum():
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Room names must be alphanumeric.\n")
            return False, username

        old_room = get_client_room(client_socket)
        if new_room == old_room:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You are already in '{new_room}'.\n")
            return False, username

        set_client_room(client_socket, new_room)
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Switched from '{old_room}' to '{new_room}'.\n")
        broadcast(f"[{timestamp()}] [SERVER]: {username} left room '{old_room}'\n", client_socket, room=old_room)
        broadcast(f"[{timestamp()}] [SERVER]: {username} joined room '{new_room}'\n", client_socket, room=new_room)
        return False, username

    if command == "/leave":
        old_room = get_client_room(client_socket)
        if old_room == DEFAULT_ROOM:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You are already in '{DEFAULT_ROOM}'.\n")
            return False, username
        set_client_room(client_socket, DEFAULT_ROOM)
        send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Returned to '{DEFAULT_ROOM}'.\n")
        broadcast(f"[{timestamp()}] [SERVER]: {username} left room '{old_room}'\n", client_socket, room=old_room)
        broadcast(f"[{timestamp()}] [SERVER]: {username} joined room '{DEFAULT_ROOM}'\n", client_socket, room=DEFAULT_ROOM)
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
        rooms_active = len(get_rooms_snapshot())
        send_to_client(
            client_socket,
            f"[{timestamp()}] [SERVER]: Users online: {users_online}, active rooms: {rooms_active}, "
            f"total chat messages: {messages_sent}\n",
        )
        return False, username

    if command == "/dm":
        if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Usage: /dm <user> <message>\n")
            return False, username

        if is_muted(client_socket):
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You are muted and cannot send DMs right now.\n")
            return False, username

        if is_rate_limited(client_socket):
            send_to_client(
                client_socket,
                f"[{timestamp()}] [SERVER]: Rate limit exceeded. Slow down and try again shortly.\n",
            )
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

    if command in {"/kick", "/mute", "/ban"}:
        if not is_admin(username):
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Admin privileges required.\n")
            return False, username

        if len(parts) < 2 or not parts[1].strip():
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Usage: {command} <user> [seconds]\n")
            return False, username

        if command == "/mute":
            mute_parts = command_line.split(" ", 2)
            if len(mute_parts) < 3:
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Usage: /mute <user> <seconds>\n")
                return False, username
            target_name = mute_parts[1].strip()
            seconds_text = mute_parts[2].strip()
            try:
                duration = int(seconds_text)
            except ValueError:
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Seconds must be an integer.\n")
                return False, username

            if duration <= 0:
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Seconds must be greater than zero.\n")
                return False, username

            target_socket = find_socket_by_username(target_name)
            if target_socket is None:
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: User '{target_name}' is not online.\n")
                return False, username

            with moderation_lock:
                muted_until[target_socket] = monotonic() + duration

            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Muted {target_name} for {duration}s.\n")
            send_to_client(target_socket, f"[{timestamp()}] [SERVER]: You are muted for {duration} seconds.\n")
            log_event(f"[MOD] {username} muted {target_name} for {duration}s")
            return False, username

        target_name = parts[1].strip()
        target_socket = find_socket_by_username(target_name)
        if target_socket is None:
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: User '{target_name}' is not online.\n")
            return False, username

        if command == "/ban":
            with moderation_lock:
                banned_usernames.add(target_name.lower())
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: Banned username '{target_name}'.\n")
            log_event(f"[MOD] {username} banned {target_name}")

        send_to_client(target_socket, f"[{timestamp()}] [SERVER]: You have been disconnected by an admin.\n")
        try:
            target_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        remove_client(target_socket)
        broadcast(f"[{timestamp()}] [SERVER]: {target_name} was removed by an admin.\n", client_socket)
        log_event(f"[MOD] {username} executed {command} on {target_name}")
        return False, username

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

        if is_username_banned(requested_name):
            send_to_client(client_socket, f"[{timestamp()}] [SERVER]: This username is banned. Connection refused.\n")
            remove_client(client_socket)
            return

        username = get_unique_username(requested_name, address[1])

        with clients_lock:
            clients[client_socket] = username
        set_client_room(client_socket, DEFAULT_ROOM)

        log_event(f"[SERVER] {username} connected from {address[0]}:{address[1]}")
        send_to_client(
            client_socket,
            f"[{timestamp()}] [SERVER]: Welcome, {username}! You are in '{DEFAULT_ROOM}'. Type /help for commands.\n",
        )
        broadcast(
            f"[{timestamp()}] [SERVER]: {username} joined room '{DEFAULT_ROOM}'\n",
            client_socket,
            room=DEFAULT_ROOM,
        )

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

            if is_muted(client_socket):
                send_to_client(client_socket, f"[{timestamp()}] [SERVER]: You are muted and cannot chat right now.\n")
                continue

            if is_rate_limited(client_socket):
                send_to_client(
                    client_socket,
                    f"[{timestamp()}] [SERVER]: Rate limit exceeded. Slow down and try again shortly.\n",
                )
                continue

            current_room = get_client_room(client_socket)
            message_id = get_next_message_id()
            formatted = f"[{timestamp()}] [#{message_id}] [{current_room}] [{username}]: {message_text}\n"
            log_event(formatted.rstrip())
            add_history(formatted)
            increment_message_count()
            delivered = broadcast(formatted, client_socket, room=current_room)
            send_to_client(
                client_socket,
                f"[{timestamp()}] [ACK #{message_id}]: Delivered to {delivered} recipient(s) in '{current_room}'.\n",
            )

    except (ConnectionResetError, BrokenPipeError, UnicodeDecodeError, OSError):
        pass
    finally:
        room = get_client_room(client_socket)
        removed_user = remove_client(client_socket)
        if removed_user:
            broadcast(
                f"[{timestamp()}] [SERVER]: {removed_user} left room '{room}'\n",
                client_socket,
                room=room,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-client TCP chat server")
    parser.add_argument("--host", default=HOST, help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT, help="Port to listen on (default: 12345)")
    parser.add_argument("--backlog", type=int, default=BACKLOG, help="Listen backlog (default: 5)")
    parser.add_argument(
        "--admins",
        default="admin",
        help="Comma-separated admin usernames (default: admin)",
    )
    parser.add_argument(
        "--rate-max",
        type=int,
        default=RATE_MAX_MESSAGES,
        help="Max messages per rate window before throttling (default: 8)",
    )
    parser.add_argument(
        "--rate-window",
        type=int,
        default=RATE_WINDOW_SECONDS,
        help="Rate limit window in seconds (default: 5)",
    )
    return parser.parse_args()


def start_server(host: str, port: int, backlog: int, admins: set[str], rate_max: int, rate_window: int) -> None:
    global ADMIN_USERS, RATE_MAX_MESSAGES, RATE_WINDOW_SECONDS
    ADMIN_USERS = admins
    RATE_MAX_MESSAGES = max(1, rate_max)
    RATE_WINDOW_SECONDS = max(1, rate_window)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(max(5, backlog))

    print(f"Server listening on {host}:{port}")
    print(f"Admin users: {', '.join(sorted(ADMIN_USERS))}")
    print(f"Rate limit: {RATE_MAX_MESSAGES} messages / {RATE_WINDOW_SECONDS} seconds")

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
    admin_names = {name.strip() for name in args.admins.split(",") if name.strip()}
    if not admin_names:
        admin_names = {"admin"}
    start_server(args.host, args.port, args.backlog, admin_names, args.rate_max, args.rate_window)