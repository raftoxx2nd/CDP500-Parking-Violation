"""
Cleanup utility for the Parking Violation Detection System.
Deletes all files from the snapshots and logs folders in the output/ directory.
"""

import os
import shutil
from pathlib import Path


def cleanup_output_folders():
    """Remove all files from snapshots and logs folders in output/."""
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "output"
    
    folders_to_clean = [
        output_dir / "snapshots",
        output_dir / "logs"
    ]
    
    for folder in folders_to_clean:
        if folder.exists():
            try:
                # Remove all files in the folder
                for file in folder.iterdir():
                    if file.is_file():
                        file.unlink()
                        print(f"Deleted: {file}")
                print(f"✓ Cleaned: {folder}")
            except Exception as e:
                print(f"✗ Error cleaning {folder}: {e}")
        else:
            print(f"⚠ Folder not found: {folder}")


if __name__ == "__main__":
    print("Starting cleanup of output folders...")
    cleanup_output_folders()
    print("Cleanup complete!")
