
from google.genai import types
try:
    print("types.Image fields:")
    if hasattr(types.Image, "model_fields"):
        for f in types.Image.model_fields:
            print(f" - {f}")
    else:
        print(dir(types.Image))
except Exception as e:
    print(e)
