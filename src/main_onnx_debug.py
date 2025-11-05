import cv2
import numpy as np
from ultralytics import YOLO
import json
import time
import os
from collections import defaultdict
import torch
import sys
import threading
import queue
import requests

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from capture.stream_handler import get_video_capture

# --- Configuration ---
ZONES_FILE = 'config/zones.json'
MODEL_PATH = 'models/yolo11s.onnx'
FIXED_VIDEO_SOURCE = "http://192.168.1.15:8080/video"
CONF_THRESHOLD = 0.3
IOU_THRESHOLD = 0.5
VIOLATION_THRESHOLD_SECONDS = 10
SNAPSHOT_DIR = 'output/snapshots'
LOG_DIR = 'output/logs'
# Define the classes you want to process (detect and display)
PROCESS_CLASSES_IDS = [2, 3]  # COCO IDs for 'car' and 'motorcycle'
# For ONNX models, device selection should be handled by ONNX Runtime, not PyTorch.
DEVICE = 'cuda' if (cv2.cuda.getCudaEnabledDeviceCount() > 0) else 'cpu'
DASHBOARD_URL = "http://localhost:8080/violation"

# Classes that trigger a violation when detected in a zone
VIOLATION_CLASSES = ['motorcycle']  # Add more class names as needed, e.g., ['motorcycle', 'car']

### --- ADDED FOR DEBUG DISPLAY --- ###
DISPLAY_WIDTH = 640 # Width for the debug window display

# --- Setup ---
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# --- (Pysource) Threaded Video Stream ---
class VideoStream:
    """A threaded video stream reader to prevent I/O blocking."""
    def __init__(self, src=0):
        self.cap = get_video_capture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Keep buffer small
        
        self.queue = queue.Queue(maxsize=1)
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        """Internal thread target function."""
        print("Video stream thread started...")
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                print("Stream thread: No frame returned, retrying...")
                self.cap.release()
                time.sleep(1)
                self.cap = get_video_capture(FIXED_VIDEO_SOURCE) # Reconnect
                continue

            if not self.queue.empty():
                try:
                    self.queue.get_nowait()  # Discard old frame
                except queue.Empty:
                    pass
            self.queue.put(frame)
    
    def read(self):
        """Read the latest frame from the queue."""
        if self.queue.empty():
            return None # No frame available yet
        return self.queue.get_nowait()

    def stop(self):
        """Stop the thread and release resources."""
        self.running = False
        self.thread.join()
        self.cap.release()
        print("Video stream thread stopped.")

### --- START OF MISSING FUNCTIONS --- ###

# --- Utility Functions ---

def load_zones(filepath=ZONES_FILE):
    """Loads zone data from the specified JSON file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Zone file not found: '{filepath}'. Please run 'define_roi.py' first.")
    with open(filepath, 'r') as f:
        data = json.load(f)
    zones = {name: np.array(poly, dtype=np.int32) for name, poly in data['zones'].items()}
    return zones, data['source_image_width'], data['source_image_height']

def scale_zones(zones, sx, sy):
    """Scales polygon coordinates by the given scaling factors."""
    scaled = {}
    for name, poly in zones.items():
        scaled[name] = np.array([[int(x * sx), int(y * sy)] for [x, y] in poly], dtype=np.int32)
    return scaled

def box_center_in_zone(box, zones):
    """Checks if the center of a bounding box is inside any of the defined zones."""
    x1, y1, x2, y2 = box
    center_point = (int((x1 + x2) / 2), int((y1 + y2) / 2))
    for name, poly in zones.items():
        if cv2.pointPolygonTest(poly, center_point, False) >= 0:
            return True, name
    return False, None

def send_to_dashboard(log_data):
    """Sends violation data to the dashboard server."""
    try:
        requests.post(DASHBOARD_URL, json=log_data, timeout=1)
        print(f"Sent violation ID {log_data['track_id']} to dashboard.")
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to dashboard server at {DASHBOARD_URL}.")
    except Exception as e:
        print(f"Error sending to dashboard: {e}")

### --- END OF MISSING FUNCTIONS --- ###


# --- Core Processing ---

def run_violation_detection():
    """Main loop for optimized real-time parking violation detection."""
    
    # 1. Load Zones
    try:
        original_zones, src_w, src_h = load_zones()
    except FileNotFoundError as e:
        print(f"❌ Error: {e}"); return

    # 2. Initialize YOLO Model
    try:
        model = YOLO(MODEL_PATH)
    except Exception as e:
        print(f"❌ Error loading YOLO model: {e}"); return

    # 3. Setup Threaded Video Capture
    video_source = FIXED_VIDEO_SOURCE
    if video_source is None:
        video_source = input("Enter video source: ")
    
    try:
        stream = VideoStream(video_source)
    except IOError as e:
        print(f"❌ Error: {e}"); return

    # 4. Get first frame for scaling
    print("Waiting for first frame from stream...")
    time.sleep(2.0)
    first_frame = stream.read()
    if first_frame is None:
        print("❌ Error: Could not get first frame from stream.")
        stream.stop(); return
        
    frame_h, frame_w = first_frame.shape[:2]
    
    # Get FPS
    fps = 30
    violation_threshold_frames = int(VIOLATION_THRESHOLD_SECONDS * fps)
    
    # 5. Scale Zones
    sx = frame_w / src_w
    sy = frame_h / src_h
    scaled_zones = scale_zones(original_zones, sx, sy)

    # 6. Initialize Tracking State
    idle_timers = defaultdict(int)
    violation_history = {}
    
    print(f"\n🚀 Starting real-time detection on {DEVICE.upper()}... Press 'q' in the window to quit.")
    
    # --- FPS & Session Tracking ---
    frame_count = 0
    start_time = time.time()
    fps = 0.0
    total_frames_processed = 0
    session_start_time = time.time()

    try:
        while True:
            frame = stream.read()
            if frame is None:
                time.sleep(0.01) # Wait for a new frame
                continue
            
            frame_count += 1
            total_frames_processed += 1

            # 7. Run Model Prediction with Tracking
            # Use model.predict() and enable tracking with the 'tracker' argument.
            # The 'persist=True' is now implied by the tracker config.
            results = model.predict(frame, verbose=False, device=DEVICE,
                                    conf=CONF_THRESHOLD, iou=IOU_THRESHOLD, classes=PROCESS_CLASSES_IDS,
                                    tracker="bytetrack.yaml")[0]

            # Process results
            for r in results:
                boxes = r.boxes
                for i, box in enumerate(boxes):
                    # --- 1. Unpack Data ---
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    label = model.names[cls_id]
                    track_id = int(box.id[0]) if box.id is not None else None

                    # Default color is green for a standard detection
                    color = (0, 255, 0)

                    # --- 2. Violation Logic (only if a track_id is assigned) ---
                    if track_id is not None:
                        is_in_zone, zone_name = box_center_in_zone((x1, y1, x2, y2), scaled_zones)

                        # Violation condition: specific classes in any zone
                        if is_in_zone and label in VIOLATION_CLASSES:
                            idle_timers[track_id] += 1
                            
                            # Yellow for potential violation
                            color = (0, 255, 255) 

                            if idle_timers[track_id] >= violation_threshold_frames:
                                # Red for confirmed violation
                                color = (0, 0, 255) 

                                if track_id not in violation_history:
                                    # --- Create Snapshot & Log ---
                                    timestamp_str = time.strftime("%Y%m%d-%H%M%S")
                                    
                                    snapshot_frame = frame.copy()
                                    cv2.polylines(snapshot_frame, [scaled_zones[zone_name]], isClosed=True, color=(0, 0, 255), thickness=2)
                                    cv2.rectangle(snapshot_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                                    text = f"ID: {track_id} ({conf:.2f})"
                                    cv2.putText(snapshot_frame, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                                    
                                    snapshot_filename = f"violation_{timestamp_str}_id{track_id}.jpg"
                                    snapshot_filename_abs = os.path.join(SNAPSHOT_DIR, snapshot_filename)
                                    cv2.imwrite(snapshot_filename_abs, snapshot_frame)
                                    
                                    log_data = {
                                        "track_id": track_id, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "zone_name": zone_name, "class_label": label, "confidence": f"{conf:.2f}",
                                        "bounding_box": [x1, y1, x2, y2],
                                        "snapshot_file": os.path.join("output", "snapshots", snapshot_filename).replace("\\", "/")
                                    }
                                    
                                    log_filename = os.path.join(LOG_DIR, f"violation_{timestamp_str}_id{track_id}.json")
                                    with open(log_filename, 'w') as f:
                                        json.dump(log_data, f, indent=4)

                                    violation_history[track_id] = zone_name
                                    print(f"🔴 VIOLATION: Vehicle ID {track_id} in '{zone_name}'.")
                                    send_to_dashboard(log_data)
                        else:
                            # Reset timer if vehicle is not in a violation zone
                            idle_timers[track_id] = 0
                    
                    # --- 3. Draw Bounding Box and Label on Frame ---
                    display_text = f"ID: {track_id} ({conf:.2f})" if track_id is not None else f"{label} ({conf:.2f})"
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, display_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            # --- 4. Prune Timers for Tracks That Have Left the Scene ---
            if results and results[0].boxes.id is not None:
                current_frame_track_ids = set(results[0].boxes.id.int().cpu().tolist())
                for track_id in list(idle_timers.keys()):
                    if track_id not in current_frame_track_ids:
                        idle_timers.pop(track_id)
                        if track_id in violation_history:
                            violation_history.pop(track_id)
                            print(f"Vehicle ID {track_id} left the scene. Reset.")

            # Draw the defined zones on the frame
            for name, poly in scaled_zones.items():
                cv2.polylines(frame, [poly], isClosed=True, color=(255, 255, 0), thickness=2) 

            # Calculate FPS
            end_time = time.time()
            elapsed = end_time - start_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                start_time = time.time()
                violation_threshold_frames = int(VIOLATION_THRESHOLD_SECONDS * fps)

            # Add FPS text to the frame
            fps_text = f"FPS: {fps:.2f} ({DEVICE.upper()})"
            cv2.putText(frame, fps_text, (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

            # 7. Display Live View
            # Resize frame for display while preserving aspect ratio
            orig_h, orig_w = frame.shape[:2]
            scale = DISPLAY_WIDTH / orig_w
            display_height = int(orig_h * scale)
            display_frame = cv2.resize(frame, (DISPLAY_WIDTH, display_height))
            cv2.imshow('Real-time Parking Violation Detection', display_frame) 

            # Check for 'q' key to quit
            if cv2.waitKey(1) & 0xFF == ord('q'): 
                print("'q' pressed. Stopping detection...")
                break

    except KeyboardInterrupt:
        print("\nStopping detection (Ctrl+C)...")
    finally:
        # 8. Cleanup
        session_end_time = time.time()
        stream.stop()
        
        cv2.destroyAllWindows() 
        
        # --- Calculate Session Statistics ---
        total_elapsed_time = session_end_time - session_start_time
        average_fps = 0
        if total_elapsed_time > 0:
            average_fps = total_frames_processed / total_elapsed_time

        print("\n--- Session Summary ---")
        if violation_history:
            print(f"Total unique violations recorded: {len(violation_history)}")
        else:
            print("No violations were recorded.")
        
        print(f"Average FPS: {average_fps:.2f}")
        print("-----------------------")


if __name__ == '__main__':
    run_violation_detection()
