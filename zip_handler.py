import os
import zipfile
from pathlib import Path
from typing import List, Optional
from utils import debug_print, calculate_md5, format_size
from datetime import datetime
import unicodedata
import tempfile
import shutil

class ZipHandler:
    def __init__(self, zip_file_path: str):
        self.zip_file_path = str(Path(zip_file_path).resolve())
        self.extract_path: Optional[str] = None
        self.media_files: List[str] = []
        self.md5_hash: Optional[str] = None
        self._file_list = None
        self._normalized_file_map = {}  # Maps normalized names to actual filenames
        # Add counters
        self._total_files = 0
        self._attachment_lookups = 0
        self._exact_matches = 0
        self._partial_matches = 0
        self._failed_lookups = 0

    def _normalize_filename(self, filename: str) -> str:
        """Normalize filename by removing emoji and special characters for comparison"""
        #debug_print(f"\n=== Normalizing filename ===", component="zip")
        #debug_print(f"Input filename: '{filename}'", component="zip")
        
        # Split filename into name and extension
        name_parts = filename.rsplit('.', 1)
        base_name = name_parts[0]
        extension = name_parts[1] if len(name_parts) > 1 else ''
        #debug_print(f"Split into: base='{base_name}', ext='{extension}'", component="zip")
        
        # Normalize the base name
        normalized = ''
        for c in base_name:
            if c.isascii() and (c.isalnum() or c in '.-_'):
                normalized += c
            elif c.isspace() and normalized and normalized[-1] != ' ':
                normalized += ' '
                
        # Combine normalized name with original extension
        result = f"{normalized.strip().lower()}.{extension.lower()}" if extension else normalized.strip().lower()
        #debug_print(f"Normalized result: '{result}'", component="zip")
        return result
        
    def get_zip_info(self):
        """Get information about the ZIP file"""
        try:
            debug_print("Getting ZIP info:", self.zip_file_path, component="zip")
            
            # Check if file exists
            if not os.path.exists(self.zip_file_path):
                raise FileNotFoundError(f"ZIP file not found: {self.zip_file_path}")
            
            # Check if it's actually a ZIP file
            if not zipfile.is_zipfile(self.zip_file_path):
                raise ValueError(f"Not a valid ZIP file: {self.zip_file_path}")
            
            zip_size = os.path.getsize(self.zip_file_path)  # Size in bytes
            zip_name = os.path.basename(self.zip_file_path)
            zip_date = datetime.fromtimestamp(os.path.getmtime(self.zip_file_path))
            
            # Calculate MD5
            try:
                self.md5_hash = calculate_md5(self.zip_file_path)
            except Exception as e:
                raise ValueError(f"Failed to calculate MD5: {str(e)}")
            
            # Check ZIP contents
            try:
                with zipfile.ZipFile(self.zip_file_path, 'r') as zip_ref:
                    content_count = len(zip_ref.namelist())
            except zipfile.BadZipFile as e:
                raise ValueError(f"Corrupted ZIP file: {str(e)}")
            
            debug_print("ZIP name:", zip_name, component="zip")
            debug_print("ZIP size:", format_size(zip_size), component="zip")
            debug_print("ZIP date:", zip_date.strftime('%d.%m.%Y %H:%M:%S'), component="zip")
            debug_print("ZIP MD5:", self.md5_hash, component="zip")
            debug_print("ZIP content count:", content_count, component="zip")
            
            return {
                'name': zip_name,
                'size': format_size(zip_size),
                'date': zip_date.strftime('%d.%m.%Y %H:%M:%S'),
                'md5': self.md5_hash,
                'content_count': content_count
            }

        except Exception as e:
            debug_print("Error getting ZIP info:", str(e), component="zip")
            raise  # Re-raise the exception to be handled by the caller

    def unpack_zip(self) -> str:
        """Unpack the ZIP file and return the extraction path"""
        debug_print("\n=== Unpacking ZIP file ===", component="zip")
        # Always calculate MD5 first
        if not self.md5_hash:
            zip_info = self.get_zip_info()
            if not zip_info or not self.md5_hash:
                raise ValueError("Could not calculate MD5 hash for ZIP file")
                
        # Create extraction path in the same directory as the input ZIP
        self.extract_path = str(Path(self.zip_file_path).parent / self.md5_hash)
        debug_print(f"Extracting ZIP to: {self.extract_path}", component="zip")
        os.makedirs(self.extract_path, exist_ok=True)
        
        with zipfile.ZipFile(self.zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(self.extract_path)
            
            # Build normalized filename map
            for root, _, files in os.walk(self.extract_path):
                for filename in files:
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, self.extract_path)
                    normalized = self._normalize_filename(rel_path)
                    self._normalized_file_map[normalized] = rel_path
                    self._total_files += 1
                        
        debug_print("ZIP extraction complete", component="zip")
        return self.extract_path

    def find_chat_file(self) -> Optional[str]:
        """Find the chat text file in the extracted directory.
        First looks for '_chat.txt', then tries a .txt file with the same name as the ZIP."""
        if not self.extract_path:
            debug_print("No extract path available", component="zip")
            return None
        
        # First try _chat.txt
        chat_file = Path(self.extract_path) / "_chat.txt"
        if chat_file.exists():
            debug_print(f"Found _chat.txt: {chat_file}", component="zip")
            return str(chat_file)
            
        # If not found, try ZIP name with .txt extension
        zip_name = Path(self.zip_file_path).stem  # Get filename without extension
        txt_file = Path(self.extract_path) / f"{zip_name}.txt"
        if txt_file.exists():
            debug_print(f"Found {zip_name}.txt: {txt_file}", component="zip")
            return str(txt_file)
            
        debug_print("No chat file found", component="zip")
        return None

    def find_attachment_file(self, filename: str) -> Optional[str]:
        """Find attachment file in extracted directory, handling emoji in filenames"""
        if not filename or not self.extract_path:
            self._failed_lookups += 1
            import traceback
            stack = ''.join(traceback.format_stack()[:-1])  # Exclude the current frame
            debug_print(f"No filename ({filename if filename else 'None'}) or extract path ({self.extract_path if self.extract_path else 'None'})\nCall stack:\n{stack}", component="zip")
            return None
            
        # Normalize the search filename
        normalized_search = self._normalize_filename(filename)
        self._attachment_lookups += 1
        debug_print(f"Finding attachment #{self._attachment_lookups}: '{filename}'", component="zip")
        
        # Look for exact match in normalized map
        if normalized_search in self._normalized_file_map:
            full_path = os.path.join(self.extract_path, self._normalized_file_map[normalized_search])
            if os.path.exists(full_path):
                self._exact_matches += 1
                #debug_print(f"Found exact match #{self._exact_matches}/{self._attachment_lookups}: {full_path}", component="zip")
                return full_path
            else:
                self._failed_lookups += 1
                debug_print(f"!!! File does not exist at path (failed: {self._failed_lookups}/{self._attachment_lookups})", component="zip")
                return None
            
        # If not found, try partial matching
        debug_print(f"\nNo exact match found. Attempting partial match (failed so far: {self._failed_lookups}). Current normalized map:", component="zip")
        for norm_name, actual_name in self._normalized_file_map.items():
            debug_print(f"  {norm_name} -> {actual_name}", component="zip")
            if normalized_search in norm_name or norm_name in normalized_search:
                full_path = os.path.join(self.extract_path, actual_name)
                if os.path.exists(full_path):
                    self._partial_matches += 1
                    debug_print(f"Found partial match #{self._partial_matches}/{self._attachment_lookups}: {full_path}", component="zip")
                    return full_path
                    
        self._failed_lookups += 1
        debug_print(f"!!! No match found (failed: {self._failed_lookups}/{self._attachment_lookups})", component="zip")
        return None

    def show_statistics(self):
        """Show ZIP handler statistics"""
        debug_print("\nZIP Handler Statistics:", component="zip")
        debug_print(f"Total files processed: {self._total_files}", component="zip")
        debug_print(f"Attachment lookups: {self._attachment_lookups}", component="zip")
        debug_print(f"Exact matches: {self._exact_matches}", component="zip")
        debug_print(f"Partial matches: {self._partial_matches}", component="zip")
        debug_print(f"Failed lookups: {self._failed_lookups}", component="zip")

    def cleanup(self):
        """Clean up temporary files"""
        if self.extract_path:
            self.show_statistics()  # Show stats before cleanup
            
            if os.path.exists(self.extract_path) and shutil.rmtree(self.extract_path):
                print(f"Removed temporary directory: {self.extract_path}")
            else:
                debug_print(f"Failed to remove temporary directory: {self.extract_path}", component="zip")
            self.extract_path = None
