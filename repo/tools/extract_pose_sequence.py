#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys
import typing

try:
    import cv2
    import mediapipe as mp
    import numpy as np

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def extract_pose_sequence(
    video_path: pathlib.Path, output_json: pathlib.Path, fps: float = 24.0
):
    print(f"Extracting pose from {video_path}...")

    if not HAS_CV2:
        print(
            "WARNING: cv2/mediapipe not found. Emitting mock pose sequence.",
            file=sys.stderr,
        )
        pose_sequence = [
            {"frame_idx": i, "timestamp_sec": round(i / fps, 4), "landmarks": []}
            for i in range(24)
        ]
        output_data = {
            "version": "pose_seq.v1",
            "video_source": str(video_path.name),
            "fps": fps,
            "frames_count": len(pose_sequence),
            "sequence": pose_sequence,
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(output_data, f, indent=2)
        return

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"ERROR: Could not open video {video_path}", file=sys.stderr)
        sys.exit(1)

    mp_pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frames_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or fps

    print(f"Video metadata: {frames_count} frames, {video_fps} FPS")

    pose_sequence = []

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = mp_pose.process(rgb_frame)

        frame_data = {
            "frame_idx": frame_idx,
            "timestamp_sec": round(frame_idx / video_fps, 4),
            "landmarks": [],
        }

        if results.pose_landmarks:
            for i, landmark in enumerate(results.pose_landmarks.landmark):
                frame_data["landmarks"].append(
                    {
                        "id": i,
                        "x": round(float(landmark.x), 6),
                        "y": round(float(landmark.y), 6),
                        "z": round(float(landmark.z), 6),
                        "visibility": round(float(landmark.visibility), 6),
                    }
                )

        pose_sequence.append(frame_data)

        if frame_idx % 24 == 0:
            print(f"Processed frame {frame_idx}/{frames_count}...")

        frame_idx += 1

    cap.release()

    output_data = {
        "version": "pose_seq.v1",
        "video_source": str(video_path.name),
        "fps": round(video_fps, 2),
        "frames_count": len(pose_sequence),
        "sequence": pose_sequence,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w") as f:
        json.dump(output_data, f, indent=2)

    print(
        f"Successfully saved {len(pose_sequence)} frames of pose data to {output_json}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract MediaPipe pose landmarks from video."
    )
    parser.add_argument("video_path", type=pathlib.Path)
    parser.add_argument("output_json", type=pathlib.Path)
    parser.add_argument("--fps", type=float, default=24.0)

    args = parser.parse_args()

    if not args.video_path.exists():
        print(f"ERROR: Input video not found: {args.video_path}", file=sys.stderr)
        sys.exit(1)

    extract_pose_sequence(args.video_path, args.output_json, args.fps)
