"""WebP file format handler"""
from typing import Optional, Tuple, List
from pathlib import Path
from PIL import Image
import os
from utils import debug_print

def check_webp_animation(file_path: str) -> Tuple[bool, Optional[Tuple[int, int]]]:
    """
    Check if a WebP file is animated and get its dimensions.
    Returns (is_animated, dimensions)
    """
    try:
        with open(file_path, 'rb') as f:
            # Check RIFF header
            if f.read(4) != b'RIFF':
                return False, None
            
            # Skip file size
            f.seek(4, 1)
            
            # Check WEBP
            if f.read(4) != b'WEBP':
                return False, None
            
            # Read chunks until we find VP8X
            while True:
                try:
                    chunk_header = f.read(4)
                    if not chunk_header:
                        break
                    
                    if chunk_header == b'VP8X':
                        # Skip 14 bytes
                        f.seek(14, 1)
                        # Check for ANIM chunk
                        is_animated = f.read(4) == b'ANIM'
                        
                        # Get dimensions using PIL
                        with Image.open(file_path) as img:
                            dimensions = img.size
                        
                        return is_animated, dimensions
                    
                    # Skip other chunks
                    chunk_size = int.from_bytes(f.read(4), 'little')
                    f.seek(chunk_size, 1)
                    
                except Exception:
                    break
            
            return False, None
            
    except Exception as e:
        debug_print(f"Error checking WebP animation: {str(e)}", component="meta")
        return False, None

def is_valid_sticker(file_path: str) -> bool:
    """
    Check if a WebP file is a valid sticker:
    - Only check dimensions
    """
    try:
        file_size = Path(file_path).stat().st_size
        debug_print(f"Checking sticker file size: {file_size} bytes", component="chat")
        
        is_animated, dimensions = check_webp_animation(file_path)
        debug_print(f"Sticker {file_path} is animated: {is_animated}, dimensions: {dimensions}", component="chat")
        
        # Only check dimensions, ignore file size
        if dimensions and dimensions[0] <= 512 and dimensions[1] <= 512:
            debug_print(f"Sticker validation: dimensions_ok=True (within 512x512)", component="chat")
            return True
        else:
            debug_print(f"Sticker validation: dimensions_ok=False (exceeds 512x512 or no dimensions)", component="chat")
            return False
            
    except Exception as e:
        debug_print(f"Error checking sticker validity: {str(e)}", component="chat")
        return False

def extract_sticker_frames(sticker_path: str, output_dir: str) -> List[str]:
    """
    Extract frames from a multiframe WebP sticker.
    Only called for stickers that are already known to be multiframe.
    
    Args:
        sticker_path: Path to the WebP sticker file
        output_dir: Directory to save the frames
        
    Returns:
        List of paths to the extracted frame files
    """
    frame_paths = []
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Extracting frames from sticker {sticker_path} to {output_dir}")
        with Image.open(sticker_path) as img:
            frame_count = 0
            while True:
                try:
                    # Save current frame
                    frame_path = os.path.join(output_dir, f"frame_{frame_count}.png")
                    img.save(frame_path, "PNG")
                    frame_paths.append(frame_path)
                    frame_count += 1
                    
                    # Move to next frame
                    img.seek(img.tell() + 1)
                except EOFError:
                    break
            print(f"Extracted {frame_count} frames from sticker {sticker_path}")
        return frame_paths
    except Exception as e:
        debug_print(f"Error extracting frames from sticker {sticker_path}: {str(e)}", component="meta")
        return []
