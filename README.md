# Real-Time Parking Violation Detection System

This project is a real-time parking violation detection system that uses YOLO object detection to identify vehicles in restricted zones. It features a comprehensive web-based dashboard for live monitoring, configuration, and alert management.

![Dashboard Screenshot](https://i.imgur.com/your-screenshot.png) <!-- It's recommended to replace this with an actual screenshot -->

## Features

- **Live Violation Feed**: View snapshots of parking violations in real-time.
- **Interactive Web Dashboard**: A user-friendly interface to monitor and control the system.
- **Web-Based Zone Editor**: Define and edit restricted parking zones directly in the browser.
- **Dynamic Video Source Configuration**: Easily switch between video files or live RTSP streams without restarting the application manually.
- **Start/Stop Control**: Start and stop the detection process from the dashboard.
- **Real-time Alerts**: Get sound and push notifications for new violations.

## Architecture

The system consists of two main components that run concurrently:

1.  **Backend Server (`src/server.py`)**: An `aiohttp` web server that serves the frontend dashboard, handles WebSocket connections for real-time updates, and manages the detection process. It acts as the main entry point for the application.
2.  **Detection Engine (`src/main_debug.py`)**: A Python script that uses a YOLO model to perform object detection and tracking on a video stream. It is launched and managed as a subprocess by the backend server. When a violation is detected, it sends the data to the server.

## Setup and Installation

The project uses a Python virtual environment to manage dependencies.

### 1. Create Environment

First, create and activate a virtual environment.

```bash
# Create the virtual environment
python -m venv .venv

# Activate on Windows
.venv\Scripts\activate

# Activate on macOS/Linux
source .venv/bin/activate
```

### 2. Install Dependencies

Install all required packages from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

## Running the Application

You only need to run the main server script. It will handle starting the detection engine automatically.

1.  **Start the Server**:
    ```bash
    python src/server.py
    ```

2.  **Access the Dashboard**:
    Open your web browser and navigate to:
    **`http://localhost:8080`**

## How to Use

1.  **Open the Dashboard**: Navigate to `http://localhost:8080`.
2.  **Set the Video Source**:
    - Click the **Settings** button.
    - In the **Video Source** tab, enter the path to a local video file (e.g., `input/video.mp4`) or the URL of a live stream (e.g., `rtsp://...`).
    - Click **Apply Source & Update Editor**. The view will automatically switch to the Zone Editor with a frame from the new source.
3.  **Define Parking Zones**:
    - In the **Zone Editor** tab, click on the image to draw the vertices of your restricted zone polygons.
    - Once a polygon is complete, click **Finish Zone** and give it a name.
    - Repeat for all desired zones.
4.  **Start Detection**:
    - Click **Save Zones & Restart**. This will save your configuration and start the detection process.
5.  **Monitor**:
    - Close the settings modal and monitor the dashboard for live violation alerts. You can start and stop the detector at any time using the controls in the header.
6.  **Enable Alerts**:
    - Click the "Enable Alerts" button to receive browser push notifications and sound alerts for new violations.
