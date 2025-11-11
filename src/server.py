import aiohttp
from aiohttp import web
import json
import os
import weakref
import subprocess
import sys
import time
import webbrowser # Optional: for auto-opening browser

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from src.capture.stream_handler import get_frame_from_source
except ImportError:
    print("Error: Could not import get_frame_from_source. Make sure stream_handler.py is accessible.")
    sys.exit(1)

print("Dashboard Server starting...")

# --- Globals ---
WS_CLIENTS = weakref.WeakSet()
detection_process = None
DETECTION_STATUS = {"status": "stopped", "pid": None}
SETTINGS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.json'))
ZONES_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'zones.json'))

# --- Subprocess Management ---
def update_detection_status():
    """Checks the subprocess and updates the global status dictionary."""
    global detection_process, DETECTION_STATUS
    
    # Store the old status to check for changes
    old_status = DETECTION_STATUS["status"]

    if detection_process and detection_process.poll() is None:
        DETECTION_STATUS = {"status": "running", "pid": detection_process.pid}
    else:
        DETECTION_STATUS = {"status": "stopped", "pid": None}
    
    # Only print if the status has actually changed
    if old_status != DETECTION_STATUS["status"]:
        print(f"Detection status changed: {DETECTION_STATUS}")
        
def stop_detection_process():
    """Stops the running detection process."""
    global detection_process
    if detection_process and detection_process.poll() is None:
        print(f"Stopping detection process with PID: {detection_process.pid}...")
        detection_process.terminate()
        try:
            detection_process.wait(timeout=5)
            print("Detection process stopped.")
        except subprocess.TimeoutExpired:
            print("Warning: Detection process did not terminate on purpose. Forcing kill.")
            detection_process.kill()
        detection_process = None
    else:
        print("Stop command received, but no detection process is running.")
    update_detection_status()

def start_detection_process():
    """Starts the main_debug.py script as a subprocess if it's not already running."""
    global detection_process
    if detection_process and detection_process.poll() is None:
        print("Start command received, but detection process is already running.")
        return
    
    print("Starting new detection process...")
    detection_script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'main_debug.py'))
    
    # Use sys.executable to ensure the same Python interpreter is used
    detection_process = subprocess.Popen([sys.executable, detection_script_path])
    print(f"Detection process started with PID: {detection_process.pid}")
    update_detection_status()

def restart_detection_process():
    """Stops the current detection process and starts a new one."""
    print("Restarting detection process...")
    stop_detection_process()
    # Add a small delay to ensure the port is released if the script uses it
    time.sleep(1) 
    start_detection_process()

# --- WebSocket Handlers ---
async def websocket_handler(request):
    """Handles new browser WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    print("Browser connected to WebSocket.")
    WS_CLIENTS.add(ws)

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'WebSocket connection closed with exception {ws.exception()}')
    finally:
        print("Browser disconnected.")
        WS_CLIENTS.discard(ws)

    return ws

# --- API Handlers ---
async def violation_handler(request):
    """
    Handles incoming violation data (HTTP POST) from the detection script.
    """
    try:
        data = await request.json()
        print(f"Received violation for ID: {data.get('track_id')}")
        
        # Broadcast the new violation data to all connected browsers
        for ws in WS_CLIENTS:
            try:
                await ws.send_json(data)
            except ConnectionResetError:
                print("Failed to send to a closed WebSocket.")
        
        return web.Response(text="OK", status=200)
    except json.JSONDecodeError:
        return web.Response(text="Bad Request: Invalid JSON", status=400)
    except Exception as e:
        print(f"Error in violation_handler: {e}")
        return web.Response(text="Internal Server Error", status=500)

async def get_detection_status_handler(request):
    """Returns the current status of the detection process."""
    update_detection_status() # Ensure status is fresh
    return web.json_response(DETECTION_STATUS)

async def start_detection_handler(request):
    """Handler to start the detection process."""
    start_detection_process()
    return web.json_response(DETECTION_STATUS)

async def stop_detection_handler(request):
    """Handler to stop the detection process."""
    stop_detection_process()
    return web.json_response(DETECTION_STATUS)

async def get_settings_handler(request):
    """Serves the current settings."""
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        return web.json_response(settings)
    except FileNotFoundError:
        return web.json_response({"error": "Settings file not found."}, status=404)
    except Exception as e:
        return web.json_response({"error": f"Failed to read settings: {e}"}, status=500)

async def set_settings_handler(request):
    """Updates settings WITHOUT restarting the detection process."""
    try:
        new_settings = await request.json()
        
        # Optional: Add validation for the new_settings format here
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(new_settings, f, indent=4)
        
        print(f"Settings updated. Source set to: {new_settings.get('video_source')}")
        # NOTE: The detection process is NO LONGER restarted here.
        # It is restarted when zones are saved.
        
        return web.json_response({"status": "success", "message": "Settings updated. Go to Zone Editor to apply."})
    except Exception as e:
        return web.json_response({"error": f"Failed to update settings: {e}"}, status=500)

async def get_frame_handler(request):
    """Captures and returns a single frame from the video source."""
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        video_source = settings.get('video_source')
        
        if not video_source:
            return web.Response(text="Video source not configured.", status=400)

        # --- FIX ---
        # The get_frame_from_source function expects a capture object, not a path.
        # We must open the capture, read one frame, and release it.
        from src.capture.stream_handler import get_video_capture
        cap = get_video_capture(video_source)
        if not cap.isOpened():
            return web.Response(text=f"Failed to open video source: {video_source}", status=500)
        
        ret, frame = cap.read()
        cap.release()
        # --- END FIX ---

        if not ret or frame is None:
            return web.Response(text="Failed to capture frame from source.", status=500)
            
        import cv2
        is_success, buffer = cv2.imencode(".jpg", frame)
        if not is_success:
            return web.Response(text="Failed to encode frame.", status=500)
            
        return web.Response(body=buffer.tobytes(), content_type='image/jpeg')

    except Exception as e:
        print(f"Error getting frame: {e}")
        return web.Response(text=f"Internal Server Error: {e}", status=500)

async def get_zones_handler(request):
    """Serves the current zones.json file."""
    if not os.path.exists(ZONES_FILE):
        return web.json_response({}) # Return empty if no zones defined
    return web.FileResponse(ZONES_FILE)

async def save_zones_handler(request):
    """Saves new zone definitions and restarts detection."""
    try:
        zones = await request.json()
        with open(ZONES_FILE, 'w') as f:
            json.dump(zones, f, indent=4)
        
        print("Zones saved. Restarting detection process to apply changes...")
        restart_detection_process() # Restart to load new zones
        
        return web.json_response({"status": "success", "message": "Zones saved and detection restarted."})
    except Exception as e:
        return web.json_response({"error": f"Failed to save zones: {e}"}, status=500)

async def list_input_files_handler(request):
    """Lists all video files in the input directory."""
    try:
        input_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'input'))
        if not os.path.exists(input_dir):
            os.makedirs(input_dir)
            return web.json_response({"files": []})
        
        # List all video files
        video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm')
        files = [f for f in os.listdir(input_dir) if f.lower().endswith(video_extensions)]
        files.sort()
        
        return web.json_response({"files": files})
    except Exception as e:
        print(f"Error listing input files: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def index_handler(request):
    """Serves the main dashboard.html file."""
    return web.FileResponse('./src/templates/dashboard.html')

def setup_app():
    """Configures and returns the aiohttp application."""
    app = web.Application()
    
    # --- Routes ---
    app.router.add_get('/', index_handler)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_post('/violation', violation_handler)
    
    # API routes for settings and zones
    app.router.add_get('/api/settings', get_settings_handler)
    app.router.add_post('/api/settings', set_settings_handler)
    app.router.add_get('/api/frame', get_frame_handler)
    app.router.add_get('/api/zones', get_zones_handler)
    app.router.add_post('/api/zones', save_zones_handler)
    app.router.add_get('/api/input-files', list_input_files_handler)

    # API routes for detection process control
    app.router.add_get('/api/detection/status', get_detection_status_handler)
    app.router.add_post('/api/detection/start', start_detection_handler)
    app.router.add_post('/api/detection/stop', stop_detection_handler)
    
    # --- Static File Serving ---
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'output'))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created static directory: {output_dir}")
        
    app.router.add_static('/output', path=output_dir, name='output')
    print(f"Serving static files from: {output_dir}")

    # Serve a general 'static' directory for assets like audio and icons
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
        print(f"Created static directory: {static_dir}")
    app.router.add_static('/static', path=static_dir, name='static')
    print(f"Serving static files from: {static_dir}")
    
    return app

if __name__ == '__main__':
    app = setup_app()
    # start_detection_process() # Optionally start detection on server launch
    print("Starting server on http://localhost:8080")
    print("View dashboard at http://localhost:8080")

    webbrowser.open_new_tab('http://localhost:8080')

    web.run_app(app, host='0.0.0.0', port=8080)
