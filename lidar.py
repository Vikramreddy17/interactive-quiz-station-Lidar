# lidar.py
"""
Quiz Arena - LD19 LiDAR Controller & Touch Processor
Reads serial telemetry from the LD19 LiDAR on COM7 (230400 baud),
transforms polar laser coordinates to a 149" x 80" calibrated interactive wall,
clusters laser hits into touch points, and transmits touch_down, touch_move,
and touch_up events via UDP to 127.0.0.1:5005.

Features:
- Full LD19 47-byte packet parser with CRC8 validation.
- Configurable wall dimensions and dead-zone boundary checks.
- Touch clustering with Euclidean distance grouping and persistence tracking.
- Interactive Tkinter visualizer showing real-time point clouds, dead zones, and touch blobs.
- Mouse simulation fallback mode when physical sensor is disconnected for easy testing.
"""

import json
import math
import os
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk

# Optional PySerial import with graceful fallback
try:
    import serial
except ImportError:
    serial = None

# ============================================================================
# WALL AND SENSOR CALIBRATION (149" x 80" Wall, 4" Dead Zones, Sensor @ 38")
# ============================================================================
FULL_W_IN = 149.0
HEIGHT_IN = 80.0
DEAD_LEFT_IN = 4.0
DEAD_RIGHT_IN = 4.0
SENSOR_Y_DEFAULT = 38.0
SENSOR_X_DEFAULT = 74.5  # Centered horizontally by default

MM = 25.4
FULL_W = FULL_W_IN * MM
HEIGHT = HEIGHT_IN * MM
X0 = DEAD_LEFT_IN * MM
X1 = (FULL_W_IN - DEAD_RIGHT_IN) * MM
ACTIVE_W = X1 - X0

PPI = 10  # 10 pixels per inch -> 1490 x 800 display canvas
WIN_W = int(FULL_W_IN * PPI)
WIN_H = int(HEIGHT_IN * PPI)

PORT = os.environ.get("LIDAR_PORT", "COM7")
BAUD = int(os.environ.get("LIDAR_BAUD", 230400))
UDP_TARGET_HOST = "127.0.0.1"
UDP_TARGET_PORT = int(os.environ.get("UDP_PORT", 5005))

# Cluster / Tracking parameters
CLUSTER_MAX_DIST_IN = 3.5    # Maximum distance (inches) between points in a touch cluster
MIN_CLUSTER_POINTS = 2       # Minimum points required to form a valid touch
TOUCH_PERSIST_FRAMES = 2     # Frames to keep touch alive when temporarily obstructed

# LD19 CRC Table
CRC_TABLE = [
    0x00, 0x4d, 0x9a, 0xd7, 0x79, 0x34, 0xe3, 0xae, 0xf2, 0xbf, 0x68, 0x25, 0x8b, 0xc6, 0x11, 0x5c,
    0xa9, 0xe4, 0x33, 0x7e, 0xd0, 0x9d, 0x4a, 0x07, 0x5b, 0x16, 0xc1, 0x8c, 0x22, 0x6f, 0xb8, 0xf5,
    0x1f, 0x52, 0x85, 0xc8, 0x66, 0x2b, 0xfc, 0xb1, 0xed, 0xa0, 0x77, 0x3a, 0x94, 0xd9, 0x0e, 0x43,
    0xb6, 0xfb, 0x2c, 0x61, 0xcf, 0x82, 0x55, 0x18, 0x44, 0x09, 0xde, 0x93, 0x3d, 0x70, 0xa7, 0xea,
    0x3e, 0x73, 0xa4, 0xe9, 0x47, 0x0a, 0xdd, 0x90, 0xcc, 0x81, 0x56, 0x1b, 0xb5, 0xf8, 0x2f, 0x62,
    0x97, 0xda, 0x0d, 0x40, 0xee, 0xa3, 0x74, 0x39, 0x65, 0x28, 0xff, 0xb2, 0x1c, 0x51, 0x86, 0xcb,
    0x21, 0x6c, 0xbb, 0xf6, 0x58, 0x15, 0xc2, 0x8f, 0xd3, 0x9e, 0x49, 0x04, 0xaa, 0xe7, 0x30, 0x7d,
    0x88, 0xc5, 0x12, 0x5f, 0xf1, 0xbc, 0x6b, 0x26, 0x7a, 0x37, 0xe0, 0xad, 0x03, 0x4e, 0x99, 0xd4,
    0x7c, 0x31, 0xe6, 0xab, 0x05, 0x48, 0x9f, 0xd2, 0x8e, 0xc3, 0x14, 0x59, 0xf7, 0xba, 0x6d, 0x20,
    0xd5, 0x98, 0x4f, 0x02, 0xac, 0xe1, 0x36, 0x7b, 0x27, 0x6a, 0xbd, 0xf0, 0x5e, 0x13, 0xc4, 0x89,
    0x63, 0x2e, 0xf9, 0xb4, 0x1a, 0x57, 0x80, 0xcd, 0x91, 0xdc, 0x0b, 0x46, 0xe8, 0xa5, 0x72, 0x3f,
    0xca, 0x87, 0x50, 0x1d, 0xb3, 0xfe, 0x29, 0x64, 0x38, 0x75, 0xa2, 0xef, 0x41, 0x0c, 0xdb, 0x96,
    0x42, 0x0f, 0xd8, 0x95, 0x3b, 0x76, 0xa1, 0xec, 0xb0, 0xfd, 0x2a, 0x67, 0xc9, 0x84, 0x53, 0x1e,
    0xeb, 0xa6, 0x71, 0x3c, 0x92, 0xdf, 0x08, 0x45, 0x19, 0x54, 0x83, 0xce, 0x60, 0x2d, 0xfa, 0xb7,
    0x5d, 0x10, 0xc7, 0x8a, 0x24, 0x69, 0xbe, 0xf3, 0xaf, 0xe2, 0x35, 0x78, 0xd6, 0x9b, 0x4c, 0x01,
    0xf4, 0xb9, 0x6e, 0x23, 0x8d, 0xc0, 0x17, 0x5a, 0x06, 0x4b, 0x9c, 0xd1, 0x7f, 0x32, 0xe5, 0xa8
]

def cal_crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = CRC_TABLE[(crc ^ b) & 0xFF]
    return crc

# ============================================================================
# LIDAR DRIVER & PARSER
# ============================================================================
class LidarDriver:
    def __init__(self, port=PORT, baud=BAUD):
        self.port = port
        self.baud = baud
        self.serial_conn = None
        self.running = False
        self.points_queue = queue.Queue(maxsize=1000)
        self.connected = False

    def connect(self):
        if not serial:
            print("[LidarDriver] PySerial not installed. Starting in Simulation mode.")
            return False
        try:
            self.serial_conn = serial.Serial(self.port, self.baud, timeout=0.1)
            self.connected = True
            print(f"[LidarDriver] Successfully connected to {self.port} @ {self.baud} baud.")
            return True
        except Exception as e:
            print(f"[LidarDriver] Could not open {self.port}: {e}")
            print("[LidarDriver] Hardware not detected. Simulation Mode enabled.")
            self.connected = False
            return False

    def read_packets(self):
        buffer = bytearray()
        while self.running:
            if not self.serial_conn or not self.connected:
                time.sleep(0.05)
                continue
            try:
                chunk = self.serial_conn.read(256)
                if not chunk:
                    continue
                buffer.extend(chunk)

                # Find LD19 packet headers (0x54, 0x2C) -> 47 bytes length
                while len(buffer) >= 47:
                    if buffer[0] == 0x54 and (buffer[1] & 0x1F) == 0x0C:
                        pkt = buffer[:47]
                        # Check CRC
                        expected_crc = pkt[46]
                        if cal_crc8(pkt[:46]) == expected_crc:
                            self._parse_packet(pkt)
                            del buffer[:47]
                        else:
                            del buffer[:1]
                    else:
                        del buffer[:1]
            except Exception as e:
                print(f"[LidarDriver] Read error: {e}")
                time.sleep(0.5)

    def _parse_packet(self, pkt):
        # Start angle (0.01 deg)
        start_angle = (pkt[4] | (pkt[5] << 8)) / 100.0
        # End angle (0.01 deg)
        end_angle = (pkt[42] | (pkt[43] << 8)) / 100.0

        if end_angle < start_angle:
            diff = (end_angle + 360.0) - start_angle
        else:
            diff = end_angle - start_angle

        step = diff / 11.0 if diff > 0 else 0

        parsed_points = []
        offset = 6
        for i in range(12):
            dist_mm = pkt[offset] | (pkt[offset + 1] << 8)
            confidence = pkt[offset + 2]
            offset += 3

            if dist_mm > 0 and confidence > 15:
                angle_deg = (start_angle + step * i) % 360.0
                parsed_points.append((angle_deg, dist_mm, confidence))

        if parsed_points:
            try:
                self.points_queue.put_nowait(parsed_points)
            except queue.Full:
                pass

    def start(self):
        self.running = True
        self.connect()
        t = threading.Thread(target=self.read_packets, daemon=True)
        t.start()

    def stop(self):
        self.running = False
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass

# ============================================================================
# TOUCH TRACKER & COORDINATE MAPPER
# ============================================================================
class TouchTracker:
    def __init__(self, udp_host=UDP_TARGET_HOST, udp_port=UDP_TARGET_PORT):
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.sensor_x_in = SENSOR_X_DEFAULT
        self.sensor_y_in = SENSOR_Y_DEFAULT
        self.sensor_angle_offset_deg = 0.0

        self.next_touch_id = 1
        self.active_touches = {}  # id -> {x, y, frames_missing}
        self.lock = threading.Lock()

    def send_event(self, event_type: str, touch_id: int, x_in: float = 0.0, y_in: float = 0.0):
        # Calculate normalized coordinates (0.0 to 1.0 within the active wall area)
        norm_x = (x_in - DEAD_LEFT_IN) / (FULL_W_IN - DEAD_LEFT_IN - DEAD_RIGHT_IN)
        norm_y = y_in / HEIGHT_IN

        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))

        payload = {
            "type": event_type,
            "id": touch_id,
            "x_inches": round(x_in, 2),
            "y_inches": round(y_in, 2),
            "x_norm": round(norm_x, 4),
            "y_norm": round(norm_y, 4)
        }

        raw_bytes = json.dumps(payload).encode("utf-8")
        try:
            self.sock.sendto(raw_bytes, (self.udp_host, self.udp_port))
        except Exception as e:
            print(f"[TouchTracker] UDP send failed: {e}")

    def polar_to_cartesian(self, angle_deg: float, dist_mm: float):
        """Converts polar angle/distance from sensor to wall inches (0..149, 0..80)."""
        rad = math.radians((angle_deg + self.sensor_angle_offset_deg) % 360.0)
        # In standard 2D wall scan:
        dist_in = dist_mm / MM
        px = self.sensor_x_in + dist_in * math.sin(rad)
        py = self.sensor_y_in + dist_in * math.cos(rad)
        return px, py

    def cluster_points(self, points):
        """Clusters nearby laser points into touch blobs."""
        clusters = []
        for p in points:
            px, py = p
            added = False
            for cluster in clusters:
                cx, cy, count = cluster["center"]
                dist = math.hypot(px - cx, py - cy)
                if dist <= CLUSTER_MAX_DIST_IN:
                    cluster["points"].append((px, py))
                    # Recalculate centroid
                    new_cx = sum(pt[0] for pt in cluster["points"]) / len(cluster["points"])
                    new_cy = sum(pt[1] for pt in cluster["points"]) / len(cluster["points"])
                    cluster["center"] = (new_cx, new_cy, len(cluster["points"]))
                    added = True
                    break
            if not added:
                clusters.append({"center": (px, py, 1), "points": [(px, py)]})

        # Filter clusters that meet minimum point threshold
        valid_blobs = []
        for c in clusters:
            if len(c["points"]) >= MIN_CLUSTER_POINTS:
                valid_blobs.append((c["center"][0], c["center"][1]))
        return valid_blobs

    def update_touches(self, detected_blobs):
        """Matches blobs against active touches to emit touch_down, touch_move, and touch_up."""
        with self.lock:
            matched_touch_ids = set()
            unmatched_blobs = list(detected_blobs)

            # Match detected blobs to existing active touches
            for touch_id, info in list(self.active_touches.items()):
                best_blob = None
                best_dist = 4.0  # Max distance to associate existing touch

                for blob in unmatched_blobs:
                    dist = math.hypot(blob[0] - info["x"], blob[1] - info["y"])
                    if dist < best_dist:
                        best_dist = dist
                        best_blob = blob

                if best_blob:
                    info["x"] = best_blob[0]
                    info["y"] = best_blob[1]
                    info["missing"] = 0
                    matched_touch_ids.add(touch_id)
                    unmatched_blobs.remove(best_blob)
                    self.send_event("touch_move", touch_id, info["x"], info["y"])
                else:
                    info["missing"] += 1
                    if info["missing"] > TOUCH_PERSIST_FRAMES:
                        self.send_event("touch_up", touch_id, info["x"], info["y"])
                        del self.active_touches[touch_id]

            # Register new touches for unmatched blobs
            for blob in unmatched_blobs:
                touch_id = self.next_touch_id
                self.next_touch_id += 1
                self.active_touches[touch_id] = {
                    "x": blob[0],
                    "y": blob[1],
                    "missing": 0
                }
                self.send_event("touch_down", touch_id, blob[0], blob[1])

# ============================================================================
# TKINTER VISUAL MONITOR & SIMULATION
# ============================================================================
class LidarMonitorApp:
    def __init__(self, root, driver: LidarDriver, tracker: TouchTracker):
        self.root = root
        self.driver = driver
        self.tracker = tracker

        self.root.title("Quiz Arena — LD19 LiDAR Controller & Touch Wall Monitor")
        self.root.geometry("1100x720")
        self.root.configure(bg="#071225")

        # Top Control Bar
        control_frame = tk.Frame(root, bg="#102540", padx=10, pady=8)
        control_frame.pack(side=tk.TOP, fill=tk.X)

        self.status_var = tk.StringVar(value="Hardware: Connecting...")
        tk.Label(control_frame, textvariable=self.status_var, font=("Segoe UI", 11, "bold"), fg="#4bdfee", bg="#102540").pack(side=tk.LEFT, padx=10)

        self.sim_label = tk.Label(control_frame, text="[Tip: Click or drag on wall canvas below to simulate LiDAR touch!]", font=("Segoe UI", 10), fg="#ffd071", bg="#102540")
        self.sim_label.pack(side=tk.RIGHT, padx=10)

        # Main Scaled Canvas (149" x 80" -> scaled down for monitor window)
        self.canvas_scale = 6.5  # Canvas scale pixels per inch
        self.canvas_w = int(FULL_W_IN * self.canvas_scale)
        self.canvas_h = int(HEIGHT_IN * self.canvas_scale)

        canvas_container = tk.Frame(root, bg="#071225", padx=20, pady=10)
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_container,
            width=self.canvas_w,
            height=self.canvas_h,
            bg="#09182d",
            highlightthickness=2,
            highlightbackground="#37577c"
        )
        self.canvas.pack(pady=10)

        # Mouse simulation events on canvas
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.mouse_touch_id = 999

        # Calibration Controls
        param_frame = tk.Frame(root, bg="#102540", padx=10, pady=8)
        param_frame.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Label(param_frame, text="Sensor X (in):", fg="#c5d9f5", bg="#102540").pack(side=tk.LEFT, padx=5)
        self.slider_x = tk.Scale(param_frame, from_=0, to=FULL_W_IN, resolution=0.5, orient=tk.HORIZONTAL, length=140, bg="#102540", fg="white", highlightthickness=0)
        self.slider_x.set(SENSOR_X_DEFAULT)
        self.slider_x.pack(side=tk.LEFT, padx=5)

        tk.Label(param_frame, text="Sensor Y (in):", fg="#c5d9f5", bg="#102540").pack(side=tk.LEFT, padx=5)
        self.slider_y = tk.Scale(param_frame, from_=0, to=HEIGHT_IN, resolution=0.5, orient=tk.HORIZONTAL, length=140, bg="#102540", fg="white", highlightthickness=0)
        self.slider_y.set(SENSOR_Y_DEFAULT)
        self.slider_y.pack(side=tk.LEFT, padx=5)

        tk.Label(param_frame, text="Angle Offset (°):", fg="#c5d9f5", bg="#102540").pack(side=tk.LEFT, padx=5)
        self.slider_angle = tk.Scale(param_frame, from_=-180, to=180, resolution=1, orient=tk.HORIZONTAL, length=140, bg="#102540", fg="white", highlightthickness=0)
        self.slider_angle.set(0)
        self.slider_angle.pack(side=tk.LEFT, padx=5)

        self.touches_label = tk.Label(param_frame, text="Active Touches: 0", font=("Segoe UI", 10, "bold"), fg="#35e0a0", bg="#102540")
        self.touches_label.pack(side=tk.RIGHT, padx=15)

        # Start render ticker
        self.current_points = []
        self.root.after(30, self.update_monitor)

    def on_mouse_down(self, event):
        x_in = event.x / self.canvas_scale
        y_in = event.y / self.canvas_scale
        self.tracker.send_event("touch_down", self.mouse_touch_id, x_in, y_in)

    def on_mouse_move(self, event):
        x_in = event.x / self.canvas_scale
        y_in = event.y / self.canvas_scale
        self.tracker.send_event("touch_move", self.mouse_touch_id, x_in, y_in)

    def on_mouse_up(self, event):
        x_in = event.x / self.canvas_scale
        y_in = event.y / self.canvas_scale
        self.tracker.send_event("touch_up", self.mouse_touch_id, x_in, y_in)

    def update_monitor(self):
        # Sync calibration sliders
        self.tracker.sensor_x_in = self.slider_x.get()
        self.tracker.sensor_y_in = self.slider_y.get()
        self.tracker.sensor_angle_offset_deg = self.slider_angle.get()

        # Update hardware status text
        if self.driver.connected:
            self.status_var.set(f"Hardware: Connected ({self.driver.port} @ {self.driver.baud})")
        else:
            self.status_var.set(f"Hardware: Disconnected (COM7 Not Found) — SIMULATION READY")

        # Drain points queue from driver
        wall_points = []
        while not self.driver.points_queue.empty():
            try:
                batch = self.driver.points_queue.get_nowait()
                for angle, dist, conf in batch:
                    px_in, py_in = self.tracker.polar_to_cartesian(angle, dist)
                    # Filter points within wall bounding box
                    if 0 <= px_in <= FULL_W_IN and 0 <= py_in <= HEIGHT_IN:
                        # Dead zone check
                        if DEAD_LEFT_IN <= px_in <= (FULL_W_IN - DEAD_RIGHT_IN):
                            wall_points.append((px_in, py_in))
            except queue.Empty:
                break

        # Process clusters and touch events
        detected_blobs = []
        if wall_points:
            detected_blobs = self.tracker.cluster_points(wall_points)
            self.tracker.update_touches(detected_blobs)

        # Draw Canvas Frame
        self.canvas.delete("all")

        # Draw Dead Zones
        dead_left_px = DEAD_LEFT_IN * self.canvas_scale
        dead_right_px = (FULL_W_IN - DEAD_RIGHT_IN) * self.canvas_scale
        self.canvas.create_rectangle(0, 0, dead_left_px, self.canvas_h, fill="#2a1820", outline="#592030")
        self.canvas.create_text(dead_left_px / 2, self.canvas_h / 2, text="DEAD\nZONE", fill="#b45b70", font=("Segoe UI", 9, "bold"), justify=tk.CENTER)

        self.canvas.create_rectangle(dead_right_px, 0, self.canvas_w, self.canvas_h, fill="#2a1820", outline="#592030")
        self.canvas.create_text(dead_right_px + (self.canvas_w - dead_right_px) / 2, self.canvas_h / 2, text="DEAD\nZONE", fill="#b45b70", font=("Segoe UI", 9, "bold"), justify=tk.CENTER)

        # Draw Active Projection Area
        self.canvas.create_rectangle(dead_left_px, 0, dead_right_px, self.canvas_h, outline="#42658a", width=2)
        self.canvas.create_text(self.canvas_w / 2, 20, text="149\" x 80\" ACTIVE INTERACTIVE PROJECTION WALL", fill="#8baecf", font=("Segoe UI", 10, "bold"))

        # Draw Sensor Position
        sx = self.tracker.sensor_x_in * self.canvas_scale
        sy = self.tracker.sensor_y_in * self.canvas_scale
        self.canvas.create_oval(sx - 8, sy - 8, sx + 8, sy + 8, fill="#ff7187", outline="#ffffff", width=2)
        self.canvas.create_text(sx, sy + 18, text="LD19 SENSOR", fill="#ff9cb0", font=("Segoe UI", 9, "bold"))

        # Draw Laser Hit Points
        for pt in wall_points:
            px = pt[0] * self.canvas_scale
            py = pt[1] * self.canvas_scale
            self.canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill="#4bdfee", outline="")

        # Draw Detected Touches
        with self.tracker.lock:
            active_count = len(self.tracker.active_touches)
            self.touches_label.config(text=f"Active Touches: {active_count}")

            for t_id, info in self.tracker.active_touches.items():
                tx = info["x"] * self.canvas_scale
                ty = info["y"] * self.canvas_scale
                # Touch ring
                self.canvas.create_oval(tx - 18, ty - 18, tx + 18, ty + 18, outline="#35e0a0", width=3)
                self.canvas.create_oval(tx - 5, ty - 5, tx + 5, ty + 5, fill="#ffd071", outline="")
                self.canvas.create_text(tx, ty - 26, text=f"TOUCH #{t_id}", fill="#35e0a0", font=("Segoe UI", 10, "bold"))

        self.root.after(30, self.update_monitor)

# ============================================================================
# MAIN APPLICATION ENTRY POINT
# ============================================================================
def main():
    print("=" * 60)
    print("  QUIZ ARENA - LD19 LIDAR CONTROLLER & TOUCH WALL")
    print(f"  Calibrated Wall: {FULL_W_IN}\" x {HEIGHT_IN}\" ({FULL_W:.0f} x {HEIGHT:.0f} mm)")
    print(f"  Dead Zones: Left {DEAD_LEFT_IN}\", Right {DEAD_RIGHT_IN}\"")
    print(f"  LiDAR Serial Target: {PORT} @ {BAUD} baud")
    print(f"  UDP Broadcast Target: {UDP_TARGET_HOST}:{UDP_TARGET_PORT}")
    print("=" * 60)

    driver = LidarDriver(port=PORT, baud=BAUD)
    tracker = TouchTracker(udp_host=UDP_TARGET_HOST, udp_port=UDP_TARGET_PORT)

    driver.start()

    root = tk.Tk()
    app = LidarMonitorApp(root, driver, tracker)

    try:
        root.mainloop()
    finally:
        print("[LiDAR] Stopping driver...")
        driver.stop()

if __name__ == "__main__":
    main()
