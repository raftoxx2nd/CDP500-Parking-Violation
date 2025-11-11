import cv2
import numpy as np
from ultralytics import YOLO
import json
import time
import os
import torch
import sys
import threading
import queue
import requests

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from capture.stream_handler import get_video_capture

# --- Configuration ---
SETTINGS_FILE = 'config/settings.json'
ZONES_FILE = 'config/zones.json'
MODEL_PATH = 'models/yolo11m.pt'
CONF_THRESHOLD = 0.3
IOU_THRESHOLD = 0.5
VIOLATION_THRESHOLD_SECONDS = 10
TRACK_GRACE_PERIOD_SECONDS = 3  # How long to wait before considering a track lost
SNAPSHOT_DIR = 'output/snapshots'
LOG_DIR = 'output/logs'
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
DASHBOARD_URL = "http://localhost:8080/violation"

### --- ADDED FOR DEBUG DISPLAY --- ###
DISPLAY_WIDTH = 1280 # Width for the debug window display

# --- Setup ---
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# --- (Pysource) Threaded Video Stream ---
class VideoStream:
    """A threaded video stream reader to prevent I/O blocking."""
    def __init__(self, src=0):
        self.source = src
        self.cap = get_video_capture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Keep buffer small
        self.is_file_source = isinstance(src, str) and os.path.exists(src)
        self.source_fps = self._determine_source_fps()
        if self.is_file_source and self.source_fps:
            self.frame_interval = 1.0 / self.source_fps
        else:
            self.frame_interval = None
        
        self.queue = queue.Queue(maxsize=1)
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _determine_source_fps(self):
        """Fetch FPS from the capture object, with sane fallbacks."""
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if fps and fps > 1:
            return fps
        if self.is_file_source:
            # Default to 30 FPS playback for files when metadata is missing.
            return 30.0
        return 0.0

    def _run(self):
        """Internal thread target function."""
        print("Video stream thread started...")
        while self.running:
            iteration_start = time.time()
            ret, frame = self.cap.read()
            if not ret:
                print("Stream thread: No frame returned, retrying...")
                self.cap.release()
                time.sleep(1)
                self.cap = get_video_capture(self.source) # Reconnect
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.source_fps = self._determine_source_fps()
                if self.is_file_source and self.source_fps:
                    self.frame_interval = 1.0 / self.source_fps
                else:
                    self.frame_interval = None
                continue

            if not self.queue.empty():
                try:
                    self.queue.get_nowait()  # Discard old frame
                except queue.Empty:
                    pass
            self.queue.put(frame)

            if self.frame_interval:
                elapsed = time.time() - iteration_start
                sleep_time = self.frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
    
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

def load_settings(filepath=SETTINGS_FILE):
    """Loads settings from the specified JSON file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Settings file not found: '{filepath}'.")
    with open(filepath, 'r') as f:
        return json.load(f)

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
    
    # 1. Load Settings
    try:
        settings = load_settings()
        video_source = settings.get('video_source')
        if not video_source:
            print("❌ Error: 'video_source' not found in settings.json")
            return
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading settings: {e}"); return

    # 2. Load Zones
    try:
        original_zones, src_w, src_h = load_zones()
    except FileNotFoundError as e:
        print(f"❌ Error: {e}"); return

    # 3. Initialize YOLO Model
    try:
        model = YOLO(MODEL_PATH)
        model.to(DEVICE)
    except Exception as e:
        print(f"❌ Error loading YOLO model: {e}"); return

    # 4. Setup Threaded Video Capture
    try:
        stream = VideoStream(video_source)
    except IOError as e:
        print(f"❌ Error: {e}"); return

    # 5. Get first frame for scaling
    print("Waiting for first frame from stream...")
    time.sleep(2.0) # Give stream time to populate
    first_frame = stream.read()
    if first_frame is None:
        print("❌ Error: Could not get first frame from stream.")
        stream.stop(); return
        
    frame_h, frame_w = first_frame.shape[:2]

    # Determine FPS baseline for stats display
    target_fps = stream.source_fps if getattr(stream, "source_fps", 0) else 30.0
    
    # 6. Scale Zones
    sx = frame_w / src_w
    sy = frame_h / src_h
    scaled_zones = scale_zones(original_zones, sx, sy)

    # 7. Initialize Tracking State
    zone_timers = {}
    violation_history = {}
    
    print(f"\n Starting real-time detection on {DEVICE.upper()}... Press 'q' in the window to quit.")
    
    # --- FPS & Session Tracking ---
    frame_count = 0
    start_time = time.time()
    processing_fps = target_fps if target_fps else 0.0
    total_frames_processed = 0
    session_start_time = time.time()

    # Main detection loop
    try:
        while True:
            frame = stream.read()
            if frame is None:
                time.sleep(0.01) # Wait for a new frame
                continue
            
            frame_count += 1
            total_frames_processed += 1

            # 7. Run Model Tracking
            results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, 
                                  device=DEVICE, conf=CONF_THRESHOLD, iou=IOU_THRESHOLD, 
                                  classes=[2, 3])[0] # 2 car, 3 motorcycle, 0 is motorcycle in custom model

            if results.boxes.id is not None:
                boxes = results.boxes.xyxy.cpu().numpy()
                track_ids = results.boxes.id.int().cpu().tolist()
                clss = results.boxes.cls.cpu().tolist()
                confs = results.boxes.conf.cpu().tolist()
                
                current_frame_track_ids = set(track_ids)
                frame_time = time.time()

                for box, track_id, cls_id, conf in zip(boxes, track_ids, clss, confs):
                    x1, y1, x2, y2 = map(int, box)
                    label = model.names[int(cls_id)]
                    
                    is_in_zone, zone_name = box_center_in_zone((x1, y1, x2, y2), scaled_zones)

                    # Default color is green
                    color = (0, 255, 0) 

                    # Violation condition: specific classes in any zone
                    if is_in_zone and label in ['motorcycle']:
                        if track_id not in zone_timers:
                            # Vehicle just entered the zone
                            zone_timers[track_id] = {
                                "enter_time": frame_time,
                                "last_seen": frame_time,
                            }
                            elapsed_in_zone = 0
                        else:
                            # Vehicle is still in the zone
                            timer_state = zone_timers[track_id]
                            elapsed_in_zone = frame_time - timer_state["enter_time"]
                            timer_state["last_seen"] = frame_time

                        # Yellow for potential violation
                        color = (0, 255, 255) 

                        if elapsed_in_zone >= VIOLATION_THRESHOLD_SECONDS:
                            # Red for confirmed violation
                            color = (0, 0, 255) 

                            if track_id not in violation_history:
                                timestamp_str = time.strftime("%Y%m%d-%H%M%S")
                                
                                # --- Create Snapshot ---
                                snapshot_frame = frame.copy() 
                                # Draw the violation zone polygon in red on the snapshot frame
                                cv2.polylines(snapshot_frame, [scaled_zones[zone_name]], isClosed=True, color=(0, 0, 255), thickness=2)
                                cv2.rectangle(snapshot_frame, (x1, y1), (x2, y2), (0, 0, 255), 2) 
                                text = f"ID: {int(track_id)} ({conf:.2f})" 
                                cv2.putText(snapshot_frame, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2) # [cite: raftoxx2nd/cdp-parking-violation/CDP-Parking-Violation-80add89edd0f763d4e0f95f31ba8742671a67dc8/main.py]
                                
                                snapshot_filename_rel = f"snapshots/violation_{timestamp_str}_id{track_id}.jpg"
                                snapshot_filename_abs = os.path.join(SNAPSHOT_DIR, f"violation_{timestamp_str}_id{track_id}.jpg")
                                cv2.imwrite(snapshot_filename_abs, snapshot_frame)
                                
                                # --- Create Log ---
                                log_data = {
                                    "track_id": track_id,
                                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "zone_name": zone_name,
                                    "class_label": label,
                                    "confidence": f"{conf:.2f}",
                                    "bounding_box": [x1, y1, x2, y2],
                                    "snapshot_file": f"output/{snapshot_filename_rel}" 
                                }
                                
                                log_filename = os.path.join(LOG_DIR, f"violation_{timestamp_str}_id{track_id}.json")
                                with open(log_filename, 'w') as f:
                                    json.dump(log_data, f, indent=4)

                                violation_history[track_id] = zone_name
                                print(f"🔴 VIOLATION: Vehicle ID {int(track_id)} in '{zone_name}'.")
                                
                                # Send to dashboard
                                threading.Thread(target=send_to_dashboard, args=(log_data,), daemon=True).start()
                    # TODO: else clause to handle vehicles outside zones but it is also handled below using grace period
                    # but I'm not sure if bounding box that dissapear in the violating zone and bounding box
                    # that appear and left the violating zone are somehow the same or no, and I don't what im doing.

                    # Draw bounding box and ID on the frame
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    text = f"ID: {int(track_id)} ({conf:.2f})"
                    cv2.putText(frame, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                # Prune timers for tracks that have been gone for the grace period
                current_time = time.time()
                for track_id in list(zone_timers.keys()):
                    # A track is considered "gone" if it hasn't been seen *inside a zone* for the grace period.
                    # The 'last_seen' timestamp is only updated when a vehicle is in a zone.
                    if current_time - zone_timers[track_id]["last_seen"] > TRACK_GRACE_PERIOD_SECONDS:
                        # If the vehicle that disappeared was a violator, log it and send event.
                        if track_id in violation_history:
                            print(f"CLEARED: Violating Vehicle ID {track_id} left the area or disappeared.")
                            # TODO: Send "violation_cleared" event to dashboard
                            violation_history.pop(track_id, None)

                        # Always remove from timers if it's gone.
                        zone_timers.pop(track_id, None)

            # Draw the defined zones on the frame
            for name, poly in scaled_zones.items():
                cv2.polylines(frame, [poly], isClosed=True, color=(255, 255, 0), thickness=2) 

            # Calculate FPS
            end_time = time.time()
            elapsed = end_time - start_time
            if elapsed >= 1.0:
                processing_fps = frame_count / elapsed
                frame_count = 0
                start_time = time.time()

            # Add FPS text to the frame
            fps_text = f"FPS: {processing_fps:.2f} ({DEVICE.upper()})"
            cv2.putText(frame, fps_text, (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

            # 7. Display Live View
            aspect_ratio = frame.shape[0] / frame.shape[1]
            display_height = int(DISPLAY_WIDTH * aspect_ratio)
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
