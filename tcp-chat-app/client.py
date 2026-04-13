import socket
import threading


HOST = "127.0.0.1"
PORT = 12345


def receive_messages(client_socket: socket.socket, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            data = client_socket.recv(4096)
            if not data:
                print("\n[INFO] Server closed the connection.")
                stop_event.set()
                break

            print(data.decode("utf-8"), end="")
        except (ConnectionResetError, OSError):
            if not stop_event.is_set():
                print("\n[INFO] Connection lost.")
                stop_event.set()
            break


def send_messages(client_socket: socket.socket, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            message = input()
        except EOFError:
            message = "/quit"
        except KeyboardInterrupt:
            message = "/quit"

        if not message:
            continue

        try:
            client_socket.sendall(message.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError):
            print("\n[INFO] Unable to send message. Server may be unavailable.")
            stop_event.set()
            break

        if message.strip() == "/quit":
            stop_event.set()
            break


def main() -> None:
    username = input("Enter username: ").strip()
    while not username:
        username = input("Username cannot be empty. Enter username: ").strip()

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((HOST, PORT))
        client_socket.sendall(username.encode("utf-8"))
    except (ConnectionRefusedError, TimeoutError, OSError):
        print(f"Could not connect to server at {HOST}:{PORT}")
        client_socket.close()
        return

    print("Connected to chat server. Type messages and press Enter to send.")
    print("Use /list to see online users, /quit to disconnect.")

    stop_event = threading.Event()

    receiver = threading.Thread(target=receive_messages, args=(client_socket, stop_event), daemon=True)
    sender = threading.Thread(target=send_messages, args=(client_socket, stop_event), daemon=True)

    receiver.start()
    sender.start()

    sender.join()
    stop_event.set()

    try:
        client_socket.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass

    client_socket.close()
    receiver.join(timeout=1)
    print("Disconnected.")


if __name__ == "__main__":
    main()