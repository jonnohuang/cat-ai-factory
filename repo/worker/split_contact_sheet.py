import argparse
import os
import pathlib
import sys

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

def split_contact_sheet(contact_sheet_path: pathlib.Path, panels_dir: pathlib.Path, rows: int = 3, cols: int = 4):
    if not contact_sheet_path.exists():
        print(f"ERROR: Contact sheet not found at {contact_sheet_path}", file=sys.stderr)
        sys.exit(1)

    panels_dir.mkdir(parents=True, exist_ok=True)

    is_mock = os.environ.get("CAF_VEO_MOCK", "").strip().lower() in ("1", "true", "yes")

    if is_mock:
        print("INFO: Mocking contact sheet splitting...")
        # In mock mode, if the sheet is empty or fake, we just create 12 dummy files
        for i in range(1, rows * cols + 1):
            panel_path = panels_dir / f"panel_{i:02d}_HD.png"
            panel_path.touch()
        print(f"Mock: Created {rows*cols} empty panels in {panels_dir}")
        return

    if not HAS_CV2:
        print("ERROR: opencv-python-headless not found. Splitting failed.", file=sys.stderr)
        sys.exit(1)

    img = cv2.imread(str(contact_sheet_path))
    if img is None:
        print(f"ERROR: Failed to read image at {contact_sheet_path}", file=sys.stderr)
        sys.exit(1)

    height, width = img.shape[:2]
    panel_h = height // rows
    panel_w = width // cols

    print(f"Splitting {width}x{height} image into {cols}x{rows} panels ({panel_w}x{panel_h} each)")

    panel_count = 0
    for r in range(rows):
        for c in range(cols):
            panel_count += 1
            y1 = r * panel_h
            y2 = (r + 1) * panel_h
            x1 = c * panel_w
            x2 = (c + 1) * panel_w

            # Crop panel
            panel = img[y1:y2, x1:x2]

            panel_filename = f"panel_{panel_count:02d}_HD.png"
            panel_path = panels_dir / panel_filename

            cv2.imwrite(str(panel_path), panel)

    print(f"SUCCESS: Split {panel_count} panels into {panels_dir}")

def main():
    parser = argparse.ArgumentParser(description="Split a storyboard contact sheet into individual panels.")
    parser.add_argument("--job", type=str, required=True, help="Path to job.json (unused but kept for contract consistency)")
    parser.add_argument("--out", type=str, required=True, help="Path to output directory")
    parser.add_argument("--rows", type=int, default=3, help="Number of rows in the contact sheet")
    parser.add_argument("--cols", type=int, default=4, help="Number of columns in the contact sheet")

    args = parser.parse_args()

    output_dir = pathlib.Path(args.out)
    contact_sheet_path = output_dir / "storyboard" / "contact_sheet.png"
    panels_dir = output_dir / "storyboard" / "panels"

    split_contact_sheet(contact_sheet_path, panels_dir, args.rows, args.cols)

if __name__ == "__main__":
    main()
