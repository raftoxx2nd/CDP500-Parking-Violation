# AI Agent Instructions for the Real-Time Parking Violation Detection System

This document provides essential guidance for an AI coding agent working on this codebase.

## 1. Big Picture Architecture

The system is composed of three main Python scripts that work together to detect and display parking violations in real-time.

- **`scripts/define_roi.py`**: A one-time setup script to define parking zones (Regions of Interest). It captures a frame from a video source, allows the user to draw polygons on it, and saves the coordinates to `config/zones.json`. **This must be run before the main application.**

- **`src/main_debug.py`**: The core detection and processing engine.
    - It reads a video stream using a dedicated `VideoStream` class in a thread to prevent I/O blocking.
    - It uses a YOLO model (`models/yolo11m.pt`) to detect and track vehicles.
    - It loads zone definitions from `config/zones.json` and checks if certain vehicles (e.g., 'motorcycle') are inside a restricted zone for a specified duration (`VIOLATION_THRESHOLD_SECONDS`).
    - On detecting a violation, it saves a snapshot and a JSON log to the `output/` directory and sends the violation data via an HTTP POST request to the `src/server.py`.

- **`src/server.py`**: An `aiohttp` web server.
    - It serves the `src/templates/dashboard.html` user interface.
    - It listens for violation data from `src/main_debug.py` on the `/violation` endpoint.
    - It uses WebSockets (`/ws`) to broadcast new violation data in real-time to all connected web clients (dashboards).
    - It statically serves the `output/` directory, allowing the dashboard to display violation snapshots.

### Data Flow

1.  `scripts/define_roi.py` -> `config/zones.json`
2.  `src/main_debug.py` reads `config/zones.json`.
3.  `src/main_debug.py` (on violation) -> `POST /violation` on `src/server.py`.
4.  `src/server.py` -> sends data via WebSocket to `dashboard.html`.

## 2. Critical Developer Workflows

### Initial Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Define Zones**: Run the interactive ROI definition tool. You will be prompted to draw polygons on a video frame.
    ```bash
    python scripts/define_roi.py
    ```

### Running the Application

The detection script and the server run as separate processes.

1.  **Start the Dashboard Server**:
    ```bash
    python src/server.py
    ```
2.  **Start the Detection Engine**:
    ```bash
    python src/main_debug.py
    ```
3.  **View the Dashboard**: Open a web browser and navigate to `http://localhost:8080`.

## 3. Key Conventions & Patterns

- **Decoupled Services**: The detection logic (`src/main_debug.py`) and the UI server (`src/server.py`) are decoupled. Communication is one-way via an HTTP POST request. This allows them to be developed and run independently.
- **Configuration**:
    - Key paths and thresholds are defined as constants at the top of each script (e.g., `ZONES_FILE`, `VIOLATION_THRESHOLD_SECONDS`).
    - Zone definitions are stored externally in `config/zones.json`.
- **Output**: All generated files (logs, snapshots) are stored in the `output/` directory. The dashboard expects to access snapshots via a URL like `/output/snapshots/filename.jpg`. When modifying file paths, ensure the web-accessible path in the log data is correct.
- **Threading for Performance**: `src/main_debug.py` uses a `VideoStream` class to read frames in a separate thread. This is a critical pattern to maintain real-time performance, as it prevents the main YOLO processing loop from being blocked by slow video I/O.
- **Violation Logic**: A violation is defined by two conditions: an object of a specific class (e.g., 'motorcycle') being inside a zone, and it remaining there for `VIOLATION_THRESHOLD_SECONDS`. The `zone_timers` dictionary in `src/main_debug.py` tracks this.
