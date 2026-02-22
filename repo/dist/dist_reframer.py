import logging
import pathlib
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("dist_reframer")

def reframe_video(
    src_path: pathlib.Path,
    dst_path: pathlib.Path,
    platform: str,
    target_fps: int = 24,
) -> None:
    """
    Reframes a 1080x1080 master into platform-specific dimensions.
    Uses blurred background padding for aspect ratio mismatches.
    """
    
    # 1. Determine Target Dimensions
    # Standard: Production Master is 1080x1080
    if platform in ["tiktok", "instagram_reels", "youtube_shorts"]:
        # 9:16
        tw, th = 1080, 1920
    elif platform in ["instagram"]:
        # 4:5
        tw, th = 1080, 1350
    elif platform in ["youtube", "twitter", "x"]:
        # 16:9 (YouTube Long / X Standard)
        tw, th = 1920, 1080
    else:
        # Fallback to no-change (passthrough)
        tw, th = 1080, 1080

    # 1.5 Safe-Zone Scaling Factor
    # On vertical platforms (9:16), we may want to slightly downscale 
    # the 1:1 master so platform UI (side icons) doesn't overlap it.
    safe_scale = 1.0
    if platform in ["tiktok", "instagram_reels", "youtube_shorts"]:
        # Scale to 92% of width to leave ~40px margin on each side
        # This keeps the square largely clear of the 150px right-side icons
        safe_scale = 0.92

    # 2. Build FFmpeg Filter Chain
    # [0:v] split [bg][fg];
    # [bg] scale=tw:th:force_original_aspect_ratio=increase,crop=tw:th,boxblur=20:10 [bgout];
    # [fg] scale=tw*safe_scale:th*safe_scale:force_original_aspect_ratio=decrease [fgout];
    # [bgout][fgout] overlay=(W-w)/2:(H-h)/2 [out]
    
    fg_w = int(tw * safe_scale)
    fg_h = int(th * safe_scale)

    vf = (
        f"split [bg][fg]; "
        f"[bg] scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=20:10 [bgout]; "
        f"[fg] scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease [fgout]; "
        f"[bgout][fgout] overlay=(W-w)/2:(H-h)/2 [out]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-r", str(target_fps),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",  # Preserve audio
        "-movflags", "+faststart",
        str(dst_path)
    ]

    print(f"INFO: Reframing {src_path.name} -> {platform} ({tw}x{th})")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        logger.error(f"Reframing failed for {platform}: {e}")
        raise RuntimeError(f"FFmpeg failed: {e}")

if __name__ == "__main__":
    # Minimal CLI for testing
    import argparse
    parser = argparse.ArgumentParser(description="Standalone Reframer")
    parser.add_argument("--src", required=True, help="Source 1:1 MP4")
    parser.add_argument("--dst", required=True, help="Output MP4")
    parser.add_argument("--platform", required=True, help="Target platform")
    args = parser.parse_args()
    
    reframe_video(pathlib.Path(args.src), pathlib.Path(args.dst), args.platform)
