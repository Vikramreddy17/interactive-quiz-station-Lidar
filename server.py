# server.py
"""
Quiz Arena - Python Backend Server
Provides:
- Static HTML serving for the interactive quiz game.
- REST API for dynamic question fetching and score registration.
- Leaderboard persistence and protected Hall of Fame admin reset.
- UDP listener for LiDAR touch events, broadcasted via Server-Sent Events (SSE).
"""

import hmac
import json
import math
import os
import queue
import socket
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from question_provider import (
    CATEGORIES,
    DIFFICULTIES,
    QUESTION_COUNT,
    TIME_LIMIT,
    choose_questions,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
LEADERBOARD_FILE = DATA / "leaderboard.json"

HTTP_HOST = "127.0.0.1"
HTTP_PORT = int(os.environ.get("HTTP_PORT", 8000))
UDP_HOST = "127.0.0.1"
UDP_PORT = int(os.environ.get("UDP_PORT", 5005))
ADMIN_PIN = os.environ.get("QUIZ_ADMIN_PIN", "1234").strip()

LOCK = threading.RLock()
subscribers_lock = threading.Lock()
event_subscribers = []

# ============================================================================
# LEADERBOARD HELPERS
# ============================================================================
def load_leaderboard():
    with LOCK:
        if not LEADERBOARD_FILE.exists():
            return []
        try:
            with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            print(f"[Server] Error reading leaderboard.json: {e}")
            return []

def save_leaderboard(entries):
    with LOCK:
        temp_file = LEADERBOARD_FILE.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
            temp_file.replace(LEADERBOARD_FILE)
        except Exception as e:
            print(f"[Server] Error writing leaderboard.json: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

def sort_leaderboard(entries):
    # Sort criteria: Highest score first, then lowest total_time, then earliest timestamp
    return sorted(
        entries,
        key=lambda x: (
            -int(x.get("score", 0)),
            float(x.get("total_time", 9999)),
            x.get("timestamp", "")
        )
    )

# ============================================================================
# UDP LIDAR LISTENER -> SSE QUEUE BROADCAST
# ============================================================================
def udp_listener_thread():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((UDP_HOST, UDP_PORT))
        print(f"[LiDAR Bridge] Listening for touch events on UDP {UDP_HOST}:{UDP_PORT}")
    except Exception as e:
        print(f"[LiDAR Bridge] Could not bind UDP socket {UDP_HOST}:{UDP_PORT}: {e}")
        return

    while True:
        try:
            data, _ = sock.recvfrom(4096)
            text = data.decode("utf-8", errors="ignore").strip()
            if not text:
                continue

            # Validate that payload is JSON
            try:
                json.loads(text)
            except Exception:
                continue

            # Broadcast to all connected SSE clients
            with subscribers_lock:
                dead_subs = []
                for sub_queue in event_subscribers:
                    try:
                        sub_queue.put_nowait(text)
                    except queue.Full:
                        # Drop oldest or mark dead
                        pass
        except Exception as e:
            print(f"[LiDAR Bridge] UDP receive error: {e}")

# ============================================================================
# HTTP REQUEST HANDLER
# ============================================================================
class QuizHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Clean logging: suppress noisy SSE keepalive logs
        if "api/events" not in args[0]:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} - {args[1]}")

    def send_json(self, status_code, obj):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Pin")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        pathname = parsed.path

        # Static index.html
        if pathname in ("/", "/index.html"):
            index_path = ROOT / "index.html"
            if index_path.exists():
                try:
                    with open(index_path, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    self.send_error(500, f"Error reading index.html: {e}")
                    return
            else:
                self.send_error(404, "index.html not found.")
                return

        # API: Questions
        if pathname == "/api/questions":
            qs = parse_qs(parsed.query)
            category = qs.get("category", ["tech"])[0]
            difficulty = qs.get("difficulty", ["medium"])[0]

            try:
                questions = choose_questions(category, difficulty)
                self.send_json(200, {
                    "category": category,
                    "difficulty": difficulty,
                    "count": len(questions),
                    "questions": questions
                })
            except Exception as e:
                print(f"[Server] Error generating questions: {e}")
                self.send_json(500, {"error": "Failed to generate questions"})
            return

        # API: Leaderboard
        if pathname == "/api/leaderboard":
            entries = load_leaderboard()
            sorted_entries = sort_leaderboard(entries)
            self.send_json(200, {
                "count": len(sorted_entries),
                "entries": sorted_entries
            })
            return

        # API: Server-Sent Events (SSE) for LiDAR touch stream
        if pathname == "/api/events":
            client_queue = queue.Queue(maxsize=120)
            with subscribers_lock:
                event_subscribers.append(client_queue)

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            # Initial connection handshake
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()

                while True:
                    try:
                        event_text = client_queue.get(timeout=10.0)
                        payload = f"data: {event_text}\n\n".encode("utf-8")
                        self.wfile.write(payload)
                        self.wfile.flush()
                    except queue.Empty:
                        # Heartbeat ping to prevent network timeout
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                pass
            finally:
                with subscribers_lock:
                    if client_queue in event_subscribers:
                        event_subscribers.remove(client_queue)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        pathname = parsed.path

        if pathname == "/api/scores":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))

                name = str(data.get("name", "ANONYMOUS")).strip().upper()[:24]
                if not name:
                    name = "ANONYMOUS"

                category = str(data.get("category", "tech")).strip()
                difficulty = str(data.get("difficulty", "medium")).strip()
                score = int(data.get("score", 0))
                correct = int(data.get("correct", 0))
                wrong = int(data.get("wrong", 0))
                unanswered = int(data.get("unanswered", 0))
                total_time = round(float(data.get("total_time", 0.0)), 1)
                accuracy = round((correct / QUESTION_COUNT * 100), 1) if QUESTION_COUNT > 0 else 0.0

                category_name = CATEGORIES.get(category, {}).get("name", category.capitalize())
                difficulty_name = DIFFICULTIES.get(difficulty, difficulty.capitalize())

                entry = {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "category": category,
                    "category_name": category_name,
                    "difficulty": difficulty,
                    "difficulty_name": difficulty_name,
                    "score": score,
                    "correct": correct,
                    "wrong": wrong,
                    "unanswered": unanswered,
                    "question_count": QUESTION_COUNT,
                    "accuracy": accuracy,
                    "total_time": total_time,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                with LOCK:
                    current_entries = load_leaderboard()
                    current_entries.append(entry)
                    sorted_entries = sort_leaderboard(current_entries)
                    # Keep all historical entries (or up to 500)
                    save_leaderboard(sorted_entries[:500])

                print(f"[Score] {name} completed {category_name} ({difficulty_name}): {score} pts ({correct}/{QUESTION_COUNT})")
                self.send_json(200, {"status": "ok", "entry": entry})
            except Exception as e:
                print(f"[Server] Error saving score: {e}")
                self.send_json(400, {"error": "Invalid score payload"})
            return

        self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        pathname = parsed.path

        # Admin reset for Hall of Fame
        if pathname == "/api/admin/leaderboard":
            provided_pin = self.headers.get("X-Admin-Pin", "").strip()

            # Secure constant-time comparison to prevent timing attacks
            if not hmac.compare_digest(provided_pin, ADMIN_PIN):
                print(f"[Admin] Unauthorized leaderboard reset attempt with PIN: {provided_pin}")
                self.send_json(401, {"error": "Invalid admin PIN. Access denied."})
                return

            try:
                # Reset leaderboard.json only; leaves question cache & history untouched
                save_leaderboard([])
                print("[Admin] Hall of Fame leaderboard has been successfully reset.")
                self.send_json(200, {
                    "status": "ok",
                    "message": "Hall of Fame leaderboard cleared successfully."
                })
            except Exception as e:
                print(f"[Admin] Error during leaderboard reset: {e}")
                self.send_json(500, {"error": "Failed to clear leaderboard."})
            return

        self.send_error(404, "Not Found")


def run():
    # Start UDP listener in daemon thread
    udp_thread = threading.Thread(target=udp_listener_thread, daemon=True)
    udp_thread.start()

    server = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), QuizHTTPHandler)
    print("=" * 60)
    print("  QUIZ ARENA - INTERACTIVE QUIZ BACKEND SERVER")
    print(f"  HTTP Interface: http://{HTTP_HOST}:{HTTP_PORT}")
    print(f"  LiDAR UDP Ingest: udp://{UDP_HOST}:{UDP_PORT}")
    print(f"  Admin PIN: {'*' * len(ADMIN_PIN)} (configured via QUIZ_ADMIN_PIN)")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] Shutting down Quiz Arena server...")
        server.shutdown()

if __name__ == "__main__":
    run()

