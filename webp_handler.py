"""WebP file format handler"""
from typing import Optional, Tuple
from pathlib import Path
from PIL import Image

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
        print(f"Error checking WebP animation: {str(e)}")
        return False, None

def is_valid_sticker(file_path: str) -> bool:
    """
    Check if a WebP file is a valid sticker:
    - Static stickers must be <= 100KB
    - Animated stickers must be <= 500KB and 512x512 pixels
    """
    try:
        file_size = Path(file_path).stat().st_size
        is_animated, dimensions = check_webp_animation(file_path)
        
        if is_animated:
            return (file_size <= 500 * 1024 and  # 500KB
                    dimensions == (512, 512))
        else:
            return file_size <= 100 * 1024  # 100KB
            
    except Exception as e:
        print(f"Error checking sticker validity: {str(e)}")
        return False
