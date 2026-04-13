# Multi-Client TCP Chat App (Python)

This project is a terminal-based multi-client chat application built with Python's built-in `socket` and `threading` modules.

It demonstrates:
- TCP client-server communication
- Real-time message broadcasting to multiple clients
- Concurrent I/O using threads
- Graceful handling of disconnects and broken connections
- UTF-8 encoding/decoding for all network data

## Project Structure

```text
tcp-chat-app/
├── server.py
├── client.py
└── README.md
```

## How to Run

1. Start the server:

```bash
python server.py
```

2. Start one or more clients in separate terminals:

```bash
python client.py
```

3. Enter a username in each client when prompted, then start chatting.

## Commands

- Normal text: sends a chat message to all other clients
- `/list`: shows currently online users
- `/quit`: disconnects the client cleanly

## Notes

- Default host/port are `127.0.0.1:12345`.
- The server listens with backlog `5` and supports multiple simultaneous clients.
- Messages are not echoed back to the sender.
- Server logs connection events and chat messages into `chat_log.txt`.