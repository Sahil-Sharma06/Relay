# Multi-Client TCP Chat Application

A terminal-based real-time chat system built in Python using only built-in libraries.

This project uses a client-server architecture:
- `server.py` handles multiple client connections and message routing.
- `client.py` lets each user send and receive messages simultaneously.

## Features

- Multi-client TCP chat using sockets
- Threaded server (one handler thread per client)
- Threaded client (separate send/receive threads)
- Username-based identity for each user
- Broadcast messaging (no echo back to sender)
- Private messaging with `/dm`
- Room-based messaging (`/join`, `/leave`, `/rooms`, `/where`)
- Delivery receipts with message IDs
- Message history and server statistics
- Admin moderation commands (`/kick`, `/mute`, `/ban`)
- Rate limiting to reduce spam
- Graceful disconnect handling
- UTF-8 encoding/decoding for all network data

## Tech Stack

- Python 3
- `socket`
- `threading`
- `argparse`
- `collections` and `datetime`

## Project Structure

```text
tcp-chat-app/
├── server.py
├── client.py
└── README.md
```

## Setup and Run

1. Open terminal in project root.
2. (Optional) activate virtual environment.
3. Start server:

```bash
cd tcp-chat-app
python server.py --host 127.0.0.1 --port 12345 --backlog 10
```

4. Open separate terminals for clients and run:

```bash
cd tcp-chat-app
python client.py --host 127.0.0.1 --port 12345
```

5. Enter username in each client and start chatting.

## Server Options

```bash
python server.py --host 127.0.0.1 --port 12345 --backlog 10 --admins admin,alice --rate-max 8 --rate-window 5
```

- `--host`: interface to bind
- `--port`: server port
- `--backlog`: listen backlog
- `--admins`: comma-separated admin usernames
- `--rate-max`: max messages per window
- `--rate-window`: rate limit window in seconds

## Chat Commands

- Normal text: send message to users in your room
- `/help`: show commands
- `/list`: list online users with room info
- `/rooms`: show active rooms
- `/where`: show your current room
- `/join <room>`: join a room
- `/leave`: return to lobby
- `/dm <user> <message>`: private message
- `/rename <new_name>`: change username
- `/history [n]`: show last `n` messages
- `/stats`: show server stats
- `/kick <user>`: admin only
- `/mute <user> <seconds>`: admin only
- `/ban <user>`: admin only
- `/quit`: disconnect cleanly
- `/clear`: client-only command to clear terminal

## What This Project Demonstrates

- Network programming fundamentals with TCP
- Concurrency with threads
- Shared-state synchronization using locks
- Protocol-style command parsing
- Reliability features (acknowledgements, moderation, throttling)