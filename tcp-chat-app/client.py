import argparse
import os
import socket
import threading


HOST = "127.0.0.1"
PORT = 12345


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-client TCP chat client")
    parser.add_argument("--host", default=HOST, help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT, help="Server port (default: 12345)")
    return parser.parse_args()


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

        if message.strip() == "/clear":
            os.system("cls")
            print("[INFO] Screen cleared. Type /help to see server commands.")
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
    args = parse_args()

    username = input("Enter username: ").strip()
    while not username:
        username = input("Username cannot be empty. Enter username: ").strip()

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((args.host, args.port))
        client_socket.sendall(username.encode("utf-8"))
    except (ConnectionRefusedError, TimeoutError, OSError):
        print(f"Could not connect to server at {args.host}:{args.port}")
        client_socket.close()
        return

    print("Connected to chat server. Type messages and press Enter to send.")
    print("Use /help to see all server commands. Local command: /clear.")

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