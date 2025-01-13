import hashlib
import datetime
import os
from pathlib import Path

DEBUG = False
DEBUG_ATTACHMENTS = False
DEBUG_FILES = {}  # Dictionary to store file handles for each component
DEBUG_BASE_PATH = None

def debug_print(*messages: str, component: str = None) -> None:
    """Print debug messages if DEBUG is True"""
    if DEBUG:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        message = f"[{timestamp}] " + " ".join(str(m) for m in messages)
        
        if component and component in DEBUG_FILES:
            DEBUG_FILES[component].write(message + "\n")
            DEBUG_FILES[component].flush()

def debug_attachment_print(message: str, component: str = None) -> None:
    """Print debug messages for attachments if DEBUG_ATTACHMENTS is True"""
    if DEBUG_ATTACHMENTS:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        message = f"[{timestamp}] [ATTACHMENT] {message}"
        if component and component in DEBUG_FILES:
            DEBUG_FILES[component].write(message + "\n")
            DEBUG_FILES[component].flush()

def init_debug_file(zip_path: str) -> None:
    """Initialize debug files next to the zip file"""
    global DEBUG_FILES, DEBUG_BASE_PATH
    if DEBUG:
        debug_dir = os.path.dirname(os.path.abspath(zip_path))
        base_name = os.path.splitext(os.path.basename(zip_path))[0]
        DEBUG_BASE_PATH = os.path.join(debug_dir, f"{base_name}_debug")
        
        # Create debug files for each component
        components = ['main', 'zip', 'chat', 'meta', 'pdf']
        for comp in components:
            debug_path = f"{DEBUG_BASE_PATH}_{comp}.log"
            DEBUG_FILES[comp] = open(debug_path, 'w', encoding='utf-8')
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            DEBUG_FILES[comp].write(f"[{timestamp}] Debug log started for {comp}\n")
            DEBUG_FILES[comp].flush()
        
        print("Debug files created:")
        for comp in components:
            print(f"  {base_name}_debug_{comp}.log")

def close_debug_file() -> None:
    """Close all debug files"""
    global DEBUG_FILES
    for component, file in DEBUG_FILES.items():
        if file:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            file.write(f"[{timestamp}] Debug log ended for {component}\n")
            file.flush()
            file.close()
    DEBUG_FILES = {}

def calculate_md5(file_path: str) -> str:
    """Calculate MD5 hash of a file"""
    try:
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            # Read the file in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except Exception as e:
        debug_print(f"Error calculating MD5: {str(e)}", component="zip")
        raise ValueError(f"Failed to calculate MD5 for {file_path}: {str(e)}")

def format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"
