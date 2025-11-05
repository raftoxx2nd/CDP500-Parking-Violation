# scripts/convert_model.py

from ultralytics import YOLO
import os

# --- Configuration ---
# Assumes the script is run from the project's root directory.
# Example: python scripts/convert_model.py
MODEL_DIR = "models"
INPUT_MODEL_NAME = "yolo11s.pt" # The model mentioned in your architecture doc
# --- End Configuration ---

def convert_to_onnx():
    """
    Loads a YOLO .pt model and exports it to ONNX format.
    The output file will be saved in the same directory with a .onnx extension.
    """
    input_model_path = os.path.join(MODEL_DIR, INPUT_MODEL_NAME)

    if not os.path.exists(input_model_path):
        print(f"Error: Model file not found at '{input_model_path}'")
        print("Please ensure the model exists and you are running this script from the project root directory.")
        return

    try:
        print(f"Loading model from '{input_model_path}'...")
        # Load the YOLO model
        model = YOLO(input_model_path)

        print("Starting ONNX export...")
        # Export the model to ONNX format. The output will be 'models/yolo11m.onnx'
        model.export(format='onnx')

        output_model_name = INPUT_MODEL_NAME.replace('.pt', '.onnx')
        print(f"\n✅ Successfully converted model to '{os.path.join(MODEL_DIR, output_model_name)}'")

    except Exception as e:
        print(f"\n❌ An error occurred during conversion: {e}")
        print("Please ensure 'ultralytics' and 'onnx' are installed (`pip install ultralytics onnx`).")


if __name__ == "__main__":
    convert_to_onnx()