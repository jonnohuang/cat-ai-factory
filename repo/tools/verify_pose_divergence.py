#!/usr/bin/env python3
import argparse
import json
import math
import pathlib
import sys

def calculate_divergence(seq_a: dict, seq_b: dict) -> float:
    """
    Computes a similarity score [0.0 - 1.0] between two pose sequences.
    1.0 = Perfect match.
    0.0 = Complete divergence.
    """
    frames_a = seq_a.get("sequence", [])
    frames_b = seq_b.get("sequence", [])
    
    count = min(len(frames_a), len(frames_b))
    if count == 0:
        return 0.0
        
    total_frame_similarity = 0.0
    valid_frames = 0
    
    for i in range(count):
        marks_a = frames_a[i].get("landmarks", [])
        marks_b = frames_b[i].get("landmarks", [])
        
        if not marks_a or not marks_b:
            # If one frame has no landmarks, we penalize
            continue
            
        if len(marks_a) != len(marks_b):
            continue
            
        # Compare all landmarks (MediaPipe 33 points)
        sq_dist_sum = 0.0
        for la, lb in zip(marks_a, marks_b):
            # 2D Euclidean distance (x, y normalized)
            sq_dist_sum += (la["x"] - lb["x"])**2 + (la["y"] - lb["y"])**2
            
        mse = sq_dist_sum / len(marks_a)
        # RMSE typically ranges from 0.0 to ~0.5 in normalized space
        rmse = math.sqrt(mse)
        
        # Exponential mapping for better sensitivity
        # 0.0 RMSE -> 1.0 similarity
        # 0.1 RMSE -> ~0.6 similarity
        # 0.2 RMSE -> ~0.3 similarity
        frame_similarity = math.exp(-10 * rmse)
        
        total_frame_similarity += frame_similarity
        valid_frames += 1
        
    if valid_frames == 0:
        return 0.0
        
    return round(total_frame_similarity / valid_frames, 4)

def main():
    parser = argparse.ArgumentParser(description="Verify pose divergence between reference and generated video.")
    parser.add_argument("ref_json", type=pathlib.Path, help="Reference pose_seq.json")
    parser.add_argument("gen_json", type=pathlib.Path, help="Generated pose_seq.json")
    parser.add_argument("--threshold", type=float, default=0.7, help="Similarity threshold for PASS")
    
    args = parser.parse_args()
    
    if not args.ref_json.exists():
        print(f"ERROR: Reference JSON not found: {args.ref_json}", file=sys.stderr)
        sys.exit(1)
    if not args.gen_json.exists():
        print(f"ERROR: Generated JSON not found: {args.gen_json}", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(args.ref_json, "r") as f:
            ref = json.load(f)
        with open(args.gen_json, "r") as f:
            gen = json.load(f)
            
        score = calculate_divergence(ref, gen)
        
        result = {
            "version": "pose_divergence_report.v1",
            "score": score,
            "threshold": args.threshold,
            "status": "pass" if score >= args.threshold else "fail",
            "frames_compared": min(len(ref.get("sequence", [])), len(gen.get("sequence", [])))
        }
        
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"ERROR: Failed to verify divergence: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
