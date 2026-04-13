# Multi-Client TCP Chat App (Python)

This project is a terminal-based multi-client chat application built with Python's built-in `socket` and `threading` modules.

It demonstrates:
- TCP client-server communication
- Real-time message broadcasting to multiple clients
- Concurrent I/O using threads
- Graceful handling of disconnects and broken connections
- UTF-8 encoding/decoding for all network data
- Command parsing and stateful server features (DMs, rename, history, stats)
- Room/channel based chat routing
- Delivery receipts with server-assigned message IDs
- Rate limiting and moderation controls

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

Optional server arguments:

```bash
python server.py --host 127.0.0.1 --port 12345 --backlog 10
```

Interview/demo-friendly startup with admin and throttling config:

```bash
python server.py --host 127.0.0.1 --port 12345 --admins admin,alice --rate-max 8 --rate-window 5
```

2. Start one or more clients in separate terminals:

```bash
python client.py
```

Optional client arguments:

```bash
python client.py --host 127.0.0.1 --port 12345
```

3. Enter a username in each client when prompted, then start chatting.

## Commands

- Normal text: sends a chat message to all other clients
- `/help`: shows all available commands
- `/list`: shows online users with their current room
- `/rooms`: shows active rooms and member counts
- `/where`: shows your current room
- `/join <room>`: joins a room (alphanumeric names)
- `/leave`: returns to lobby
- `/dm <user> <message>`: sends a private message
- `/rename <new_name>`: changes your display name
- `/history [n]`: shows last `n` messages from server history
- `/stats`: shows online user count and total messages sent
- `/kick <user>`: admin command to disconnect a user
- `/mute <user> <seconds>`: admin command to mute a user temporarily
- `/ban <user>`: admin command to ban a username and disconnect that user
- `/quit`: disconnects the client cleanly
- `/clear` (client local command): clears the terminal screen

## Notes

- Default host/port are `127.0.0.1:12345`.
- The server listens with backlog `5` and supports multiple simultaneous clients.
- Messages are not echoed back to the sender.
- Server logs connection events and chat messages into `chat_log.txt`.
- If a username is already in use, the server auto-adjusts it to keep usernames unique.
- Chat messages are room-scoped and include a server-assigned message ID plus delivery ACK to sender.