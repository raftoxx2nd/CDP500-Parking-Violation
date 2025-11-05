import cv2
import time

def get_video_capture(source):
    """
    Initializes and returns a cv2.VideoCapture object.
    Retries connection if it fails initially.

    Args:
        source (str or int): The video source (e.g., '0' for webcam, or path to video file/URL).

    Returns:
        cv2.VideoCapture: The video capture object.
    
    Raises:
        IOError: If the video source cannot be opened after retries.
    """
    source_str = str(source)
    if source_str.isdigit():
        source_cv = int(source_str)
    else:
        source_cv = source_str

    # Add FFMPEG backend preference for better RTSP/IP cam support
    cap = cv2.VideoCapture(source_cv, cv2.CAP_FFMPEG)
    
    if cap.isOpened():
        print(f"Successfully opened video source: {source}")
        return cap
    
    # Retry logic
    print(f"Failed to open video source: {source}. Retrying...")
    time.sleep(2.0)
    cap = cv2.VideoCapture(source_cv, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        raise IOError(f"Cannot open video source after retry: {source}")
    
    print(f"Successfully opened video source on retry: {source}")
    return cap

def get_frame_from_source(cap):
    """
    Captures a single valid frame from a video capture object.

    Args:
        cap (cv2.VideoCapture): The video capture object.

    Returns:
        numpy.ndarray: The captured frame.
    
    Raises:
        IOError: If a frame cannot be captured.
    """
    max_retries = 10
    for _ in range(max_retries):
        ret, frame = cap.read()
        if ret:
            return frame
        print("Waiting for a valid frame...")
        time.sleep(0.1) # Wait a bit before retrying
    
    raise IOError("Could not capture a valid frame from the video source.")
