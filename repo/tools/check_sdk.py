#!/usr/bin/env python3
import sys
try:
    from vertexai.preview.vision import VideoGenerationModel
    print(f"Found VideoGenerationModel: {VideoGenerationModel}")
except ImportError:
    print("VideoGenerationModel not found in vertexai.preview.vision")
except Exception as e:
    print(f"Error checking SDK: {e}")

try:
    import vertexai.generative_models
    print(f"Found GenerativeModel (Gemini): {vertexai.generative_models.GenerativeModel}")
except ImportError:
    print("GenerativeModel not found")
