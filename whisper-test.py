#!/usr/bin/env python3

import os
import sys
import torch
import whisper
import time
import warnings

# Filter out the specific FutureWarning about weights_only
warnings.filterwarnings("ignore", category=FutureWarning, 
                       message="You are using `torch.load` with `weights_only=False`.*")

def print_system_info():
    print("\n=== System Information ===")
    print(f"Python version: {sys.version.split()[0]}")
    print(f"PyTorch version: {torch.__version__}")
    print(f"Whisper version: {whisper.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
        print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")

def test_whisper_model(model_name="medium", test_file=None):
    print(f"\n=== Testing Whisper Model: {model_name} ===")
    
    # Load model and measure time
    start_time = time.time()
    print("Loading model...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # Use weights_only=True as recommended
    model = whisper.load_model(model_name, device=device)
    load_time = time.time() - start_time
    print(f"Model loaded in {load_time:.2f} seconds on {device}")
    
    # Print model size
    model_size = sum(p.numel() for p in model.parameters()) / 1e6
    print(f"Model size: {model_size:.1f}M parameters")
    
    if test_file and os.path.exists(test_file):
        print(f"\nTranscribing test file: {test_file}")
        start_time = time.time()
        result = model.transcribe(
            test_file,
            fp16=torch.cuda.is_available()
        )
        transcribe_time = time.time() - start_time
        print(f"Transcription completed in {transcribe_time:.2f} seconds")
        print("\nTranscription result:")
        print("-" * 40)
        print(result["text"].strip())
        print("-" * 40)
    else:
        print("\nNo test file provided or file not found.")
        print("To test transcription, run the script with a test audio file:")
        print(f"python {sys.argv[0]} path/to/audio/file")

if __name__ == "__main__":
    # Print system information
    print_system_info()
    
    # Get test file from command line argument
    test_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Test different model sizes
    for model_name in ["tiny", "base", "small", "medium"]:
        try:
            test_whisper_model(model_name, test_file)
        except Exception as e:
            print(f"\nError testing {model_name} model: {str(e)}")
