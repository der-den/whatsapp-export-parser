#!/usr/bin/env python3

import os
import cv2
import subprocess
import re
import hashlib
import shutil
import json
from pathlib import Path
from PIL import Image
from mutagen import File as MutagenFile
from PyPDF2 import PdfReader
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from models import ContentType, ChatMessage
from utils import debug_print
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import whisper

"""
Erstellt bzw Exrahiert für/von Attachments weitere Informationen und fügte diese als JSON Objekte der content variable hinzu. 
"""

class MetaParser:
    def __init__(self, zip_handler):
        self.zip_handler = zip_handler
        self.preview_success: Dict[ContentType, int] = {}
        self.attachment_counter = 0  # Initialize counter for attachments
        self.total_audio_files = 0  # Initialize total audio files counter
        self.current_audio_file = 0  # Initialize current audio file counter
        self.transcription_stats = {
            "transcoded": 0,
            "loaded_existing": 0,
            "errors": 0
        }

    def _calculate_md5(self, file_path: str) -> str:
        """
        Berechnet den MD5-Hash einer Datei.
        
        Args:
            file_path: Pfad zur Datei
            
        Returns:
            str: MD5-Hash der Datei
        """
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5()
                while chunk := f.read(8192):
                    file_hash.update(chunk)
            return file_hash.hexdigest()
        except Exception as e:
            print(f"Error calculating MD5 hash: {e}")
            return ""

    def _get_meta_directory(self) -> str:
        """
        Erstellt und gibt das Meta-Verzeichnis zurück, parallel zum Extraktionsverzeichnis.
        """
        # Extrahiere den Hash-Namen aus dem Extraktionspfad
        extract_dir_name = os.path.basename(self.zip_handler.extract_path)
        meta_dir = os.path.join(os.path.dirname(self.zip_handler.extract_path), f"{extract_dir_name}_meta")
        transcribe_dir = os.path.join(meta_dir, "transcribe")
        
        # Create directories if they don't exist
        os.makedirs(meta_dir, exist_ok=True)
        os.makedirs(transcribe_dir, exist_ok=True)
        
        debug_print(f"Creating meta directory: {meta_dir}", component="meta")
        
        return meta_dir

    def _transcribe_audio(self, file_path: str, audio_file: str) -> dict:
        """
        Transcribes an audio file using Whisper and returns the transcription metadata.
        
        Args:
            file_path: Path to the audio file
            audio_file: Name of the audio file
            
        Returns:
            dict: Transcription metadata including the text, model info, and any error information
        """
        result = {
            "success": False,
            "error": None,
            "error_type": None,
            "transcription": None
        }
        
        try:
            meta_dir = self._get_meta_directory()
            transcribe_dir = os.path.join(meta_dir, "transcribe")
            
            # Generate output filename based on input file
            base_name = os.path.splitext(os.path.basename(audio_file))[0]
            json_output = os.path.join(transcribe_dir, f"{base_name}_transcription.json")
            
            # Check if transcription already exists
            if os.path.exists(json_output):
                with open(json_output, 'r', encoding='utf-8') as f:
                    debug_print(f"Loading existing transcription for: {audio_file} ({self.current_audio_file}/{self.total_audio_files})")
                    saved_result = json.load(f)
                    if "error" in saved_result:
                        self.transcription_stats["errors"] += 1
                        return saved_result
                    result["transcription"] = saved_result
                    result["success"] = True
                    self.transcription_stats["loaded_existing"] += 1
                    return result
            
            # Load Whisper model (using "base" for a balance of speed and accuracy)
            import whisper
            import warnings
            
            # Specifically catch and suppress the torch.load warning
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=FutureWarning, 
                                     message='.*torch.load.*weights_only=False.*')
                model = whisper.load_model("large")
            
            self.current_audio_file += 1
            debug_print(f"Transcribing audio: {audio_file} ({self.current_audio_file}/{self.total_audio_files})")

            try:
                # Transcribe audio
                transcribe_result = model.transcribe(file_path)
                
                if not transcribe_result or "text" not in transcribe_result:
                    debug_print(f"Warning: No transcription result for {audio_file}")
                    result["error"] = "No transcription result"
                    result["error_type"] = "empty_result"
                    self.transcription_stats["errors"] += 1
                    return result
                
                # Prepare metadata
                transcription_meta = {
                    "text": transcribe_result["text"],
                    "model": "whisper-base",
                    "language": transcribe_result.get("language", "unknown"),
                    "segments": transcribe_result.get("segments", []),
                    "transcribed_at": datetime.now().isoformat()
                }
                
                result["transcription"] = transcription_meta
                result["success"] = True
                self.transcription_stats["transcoded"] += 1
                
                # Save transcription to file
                with open(json_output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                return result
                
            except RuntimeError as e:
                error_msg = f"CUDA/GPU error while transcribing {audio_file}: {str(e)}"
                debug_print(error_msg)
                result["error"] = error_msg
                result["error_type"] = "runtime_error"
                self.transcription_stats["errors"] += 1
                return result
            except ValueError as e:
                error_msg = f"Invalid audio format for {audio_file}: {str(e)}"
                debug_print(error_msg)
                result["error"] = error_msg
                result["error_type"] = "value_error"
                self.transcription_stats["errors"] += 1
                return result
            except Exception as e:
                error_msg = f"Unexpected error transcribing {audio_file}: {str(e)}"
                debug_print(error_msg)
                result["error"] = error_msg
                result["error_type"] = "transcribe_error"
                self.transcription_stats["errors"] += 1
                return result
            
        except Exception as e:
            error_msg = f"Error in transcription setup for {audio_file}: {e}"
            debug_print(error_msg)
            result["error"] = error_msg
            result["error_type"] = "setup_error"
            self.transcription_stats["errors"] += 1
            return result

    def _get_audio_metadata(self, audio_file: str) -> dict:
        """
        Extrahiert Metadaten von einer Audiodatei.
        
        Args:
            audio_file: Pfad zur Audiodatei
            
        Returns:
            dict: Metadaten der Audiodatei
        """
        try:
            file_path = os.path.join(self.zip_handler.extract_path, audio_file)
            audio = MutagenFile(file_path)
            
            self.attachment_counter += 1  # Increment counter
            self.total_audio_files += 1  # Increment total audio files counter
            
            metadata = {
                "type": "audio",
                "filename": audio_file,
                "attachment_number": self.attachment_counter,
                "format": audio.mime[0].split('/')[-1] if audio.mime else None,
                "duration_seconds": audio.info.length if hasattr(audio.info, 'length') else None,
                "channels": audio.info.channels if hasattr(audio.info, 'channels') else None,
                "size_bytes": os.path.getsize(file_path),
                "md5_hash": self._calculate_md5(file_path)
            }
            
            # Try to add transcription if available, but don't fail if it's not possible
            try:
                transcribe_result = self._transcribe_audio(file_path, audio_file)
                if transcribe_result["success"] and transcribe_result["transcription"]:
                    metadata["transcription"] = transcribe_result["transcription"]
                elif transcribe_result["error"]:
                    metadata["transcription_error"] = {
                        "error": transcribe_result["error"],
                        "error_type": transcribe_result["error_type"]
                    }
            except Exception as e:
                debug_print(f"Error during transcription: {e}", component="meta")
                print(f"Error during transcription: {e}")
            
            # Remove None values
            metadata = {k: v for k, v in metadata.items() if v is not None}
            
            return metadata
        except Exception as e:
            print(f"Error extracting audio metadata: {e}")
            return {"error": str(e)}

    def _get_image_metadata(self, image_file: str) -> dict:
        """
        Extrahiert Metadaten von einem Bild.
        
        Args:
            image_file: Name der Bilddatei
            
        Returns:
            dict: Metadaten des Bildes
        """
        try:
            file_path = os.path.join(self.zip_handler.extract_path, image_file)
            with Image.open(file_path) as img:
                self.attachment_counter += 1  # Increment counter
                metadata = {
                    "type": "image",
                    "filename": image_file,
                    "attachment_number": self.attachment_counter,
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "size_bytes": os.path.getsize(file_path),
                    "md5_hash": self._calculate_md5(file_path)
                }
                return metadata
        except Exception as e:
            print(f"Error extracting image metadata: {e}")
            return {"error": str(e)}

    def _get_video_metadata(self, video_file: str, preview_paths: Optional[Tuple[str, str]] = None) -> dict:
        """
        Extrahiert Metadaten von einem Video.
        
        Args:
            video_file: Pfad zum Video
            preview_paths: Optional tuple mit meta_path und report_path für Preview
            
        Returns:
            dict: Metadaten des Videos
        """
        try:
            file_path = os.path.join(self.zip_handler.extract_path, video_file)
            cap = cv2.VideoCapture(file_path)
            self.attachment_counter += 1  # Increment counter
            metadata = {
                "type": "video",
                "filename": video_file,
                "attachment_number": self.attachment_counter,
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                "fps": float(cap.get(cv2.CAP_PROP_FPS)),
                "duration_seconds": float(cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)),
                "size_bytes": os.path.getsize(file_path),
                "md5_hash": self._calculate_md5(file_path)
            }
            
            if preview_paths:
                meta_path, report_path = preview_paths
                metadata["preview"] = {
                    "meta_path": meta_path,
                    "report_path": report_path
                }
                
            cap.release()
            return metadata
        except Exception as e:
            print(f"Error extracting video metadata: {e}")
            return {"error": str(e)}

    def _get_document_metadata(self, doc_file: str) -> dict:
        """
        Extrahiert Metadaten von einem Dokument (PDF, DOCX, XLSX, PPTX).
        
        Args:
            doc_file: Pfad zum Dokument
            
        Returns:
            dict: Metadaten des Dokuments
        """
        try:
            file_path = os.path.join(self.zip_handler.extract_path, doc_file)
            file_ext = os.path.splitext(doc_file)[1].lower()
            
            self.attachment_counter += 1  # Increment counter
            metadata = {
                "type": "document",
                "filename": doc_file,
                "attachment_number": self.attachment_counter,
                "format": file_ext[1:],  # Remove the dot
                "size_bytes": os.path.getsize(file_path),
                "md5_hash": self._calculate_md5(file_path)
            }
            
            # PDF-spezifische Metadaten
            if file_ext == '.pdf':
                with open(file_path, 'rb') as file:
                    pdf = PdfReader(file)
                    info = pdf.metadata
                    if info:
                        metadata.update({
                            "title": info.get('/Title', None),
                            "author": info.get('/Author', None),
                            "page_count": len(pdf.pages)
                        })
            
            # DOCX-spezifische Metadaten
            elif file_ext == '.docx':
                doc = Document(file_path)
                core_properties = doc.core_properties
                metadata.update({
                    "title": core_properties.title,
                    "author": core_properties.author,
                    "page_count": len(doc.sections)
                })
            
            # XLSX-spezifische Metadaten
            elif file_ext == '.xlsx':
                wb = load_workbook(file_path, read_only=True)
                metadata.update({
                    "title": wb.properties.title,
                    "author": wb.properties.creator,
                    "sheet_count": len(wb.sheetnames)
                })
                wb.close()
            
            # PPTX-spezifische Metadaten
            elif file_ext == '.pptx':
                prs = Presentation(file_path)
                core_properties = prs.core_properties
                metadata.update({
                    "title": core_properties.title,
                    "author": core_properties.author,
                    "slide_count": len(prs.slides)
                })
            
            # Remove None values
            metadata = {k: v for k, v in metadata.items() if v is not None}
            
            return metadata
        except Exception as e:
            print(f"Error extracting document metadata: {e}")
            return {"error": str(e)}

    def _take_video_frames(self, video_file: str) -> Optional[Tuple[str, str]]:
        """
        Extrahiert 4 Frames aus einem Video (bei 20%, 40%, 60% und 80% der Gesamtlänge)
        und fügt sie zu einem Vorschaubild zusammen.
        
        Args:
            video_file: Der Dateiname des Videos
            
        Returns:
            Tuple[str, str]: (Relativer Pfad zum Bild im Meta-Dir, Relativer Pfad im Report) oder None bei Fehler
        """
        try:
            # Erstelle Meta-Verzeichnis und Unterverzeichnisse
            meta_dir = self._get_meta_directory()
            frames_dir = os.path.join(meta_dir, 'videoframes')
            os.makedirs(frames_dir, exist_ok=True)
            
            # Erstelle MD5-Hash des Videonamens für den Dateinamen
            video_hash = hashlib.md5(video_file.encode()).hexdigest()
            frame_file = f"{video_hash}.png"
            frame_path = os.path.join(frames_dir, frame_file)
            
            # Pfade für den Report
            report_images_dir = os.path.join(self.zip_handler.extract_path, 'html', 'images', 'videoframes')
            os.makedirs(report_images_dir, exist_ok=True)
            report_frame_path = os.path.join(report_images_dir, frame_file)
            
            # Wenn Frame bereits existiert
            if os.path.exists(frame_path):
                # Kopiere zum Report falls noch nicht vorhanden
                if not os.path.exists(report_frame_path):
                    shutil.copy2(frame_path, report_frame_path)
                return os.path.join('videoframes', frame_file), os.path.join('images', 'videoframes', frame_file)
            
            # Öffne das Video
            video_path = os.path.join(self.zip_handler.extract_path, video_file)
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                print(f"Error: Could not open video {video_file}")
                return None
            
            # Hole Video-Informationen
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                print(f"Error: Video {video_file} has no frames")
                return None
            
            # Berechne Frame-Positionen (20%, 40%, 60%, 80%)
            frame_positions = [int(total_frames * pos) for pos in [0.2, 0.4, 0.6, 0.8]]
            frames = []
            
            # Extrahiere die Frames
            for pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if ret:
                    # Konvertiere BGR zu RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                else:
                    debug_print(f"Error taking video frame: {str(e)}", component="meta")
            
            cap.release()
            
            if len(frames) != 4:
                debug_print(f"Error taking video frames: {str(e)}", component="meta")
                return None
            
            # Skaliere die Frames auf einheitliche Größe
            target_size = (320, 180)  # 16:9 Format
            scaled_frames = []
            for frame in frames:
                pil_img = Image.fromarray(frame)
                pil_img.thumbnail(target_size, Image.Resampling.LANCZOS)
                # Erstelle neues Bild mit weißem Hintergrund
                new_img = Image.new('RGB', target_size, (255, 255, 255))
                # Zentriere das Bild
                x = (target_size[0] - pil_img.size[0]) // 2
                y = (target_size[1] - pil_img.size[1]) // 2
                new_img.paste(pil_img, (x, y))
                scaled_frames.append(new_img)
            
            # Erstelle 2x2 Grid
            grid_size = (target_size[0] * 2, target_size[1] * 2)
            grid_image = Image.new('RGB', grid_size, (255, 255, 255))
            
            # Füge Frames zum Grid hinzu
            for i, frame in enumerate(scaled_frames):
                x = (i % 2) * target_size[0]
                y = (i // 2) * target_size[1]
                grid_image.paste(frame, (x, y))
            
            # Speichere das finale Bild
            grid_image.save(frame_path, 'PNG')
            
            # Kopiere zum Report
            shutil.copy2(frame_path, report_frame_path)
            
            # Logge Video und Frame-Name
            log_file = os.path.join(meta_dir, 'videoframes.log')
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{video_file}\t{frame_file}\n")
            
            return os.path.join('videoframes', frame_file), os.path.join('images', 'videoframes', frame_file)
            
        except Exception as e:
            debug_print(f"Error taking video frames: {str(e)}", component="meta")
            return None

    def _take_webpage_screenshot(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Macht einen Screenshot einer Webseite und speichert ihn als PNG.
        
        Args:
            url: Die URL der Webseite
            
        Returns:
            Tuple[str, str]: (Relativer Pfad zum Screenshot im Meta-Dir, Relativer Pfad im Report) oder None bei Fehler
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            # Erstelle Meta-Verzeichnis und Unterverzeichnisse
            meta_dir = self._get_meta_directory()
            screenshots_dir = os.path.join(meta_dir, 'linkshots')
            os.makedirs(screenshots_dir, exist_ok=True)
            
            # Erstelle MD5-Hash der URL für den Dateinamen
            url_hash = hashlib.md5(url.encode()).hexdigest()
            screenshot_file = f"{url_hash}.png"
            screenshot_path = os.path.join(screenshots_dir, screenshot_file)
            
            # Pfade für den Report
            report_images_dir = os.path.join(self.zip_handler.extract_path, 'html', 'images', 'screenshots')
            os.makedirs(report_images_dir, exist_ok=True)
            report_screenshot_path = os.path.join(report_images_dir, screenshot_file)
            
            # Wenn Screenshot bereits existiert
            if os.path.exists(screenshot_path):
                # Kopiere zum Report falls noch nicht vorhanden
                if not os.path.exists(report_screenshot_path):
                    shutil.copy2(screenshot_path, report_screenshot_path)
                return os.path.join('linkshots', screenshot_file), os.path.join('images', 'screenshots', screenshot_file)
            
            # Chrome Optionen setzen
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Starte Chrome
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                # Lade die Seite
                driver.get(url)
                driver.implicitly_wait(5)
                
                # Mache den Screenshot
                driver.save_screenshot(screenshot_path)
                debug_print(f"Taking screenshot of: {url}", component="meta")
                
                # Kopiere Screenshot in den Report
                shutil.copy2(screenshot_path, report_screenshot_path)
                
                # Logge URL und Screenshot-Name
                log_file = os.path.join(meta_dir, 'linkshots.log')
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"{url}\t{screenshot_file}\n")
                
                return os.path.join('linkshots', screenshot_file), os.path.join('images', 'screenshots', screenshot_file)
                
            finally:
                driver.quit()
                
        except Exception as e:
            debug_print(f"Error taking screenshot: {str(e)}", component="meta")
            return None

    def process_messages(self, messages: List[ChatMessage], url_pattern: str) -> Dict[ContentType, int]:
        """
        Verarbeitet eine Liste von Nachrichten, extrahiert Meta-Informationen und speichert sie als JSON im Content.
        
        Args:
            messages: Liste der Chat-Nachrichten
            url_pattern: Regex-Pattern zum Finden von URLs
            
        Returns:
            Dict[ContentType, int]: Anzahl der erfolgreichen Previews pro ContentType
        """
        total_messages = len(messages)

        for i, message in enumerate(messages):
            
            # show progress
            if i % 100 == 0 or i == total_messages - 1:
                progress = (i / total_messages) * 100
                print(f"Progress: {progress:.1f}% ({i+1}/{total_messages} messages)", end='\r')

            # Process Images
            if message.content_type.is_image and message.attachment_file:
                debug_print(f"Processing image: {message.attachment_file}", component="meta")
                try:
                    metadata = self._get_image_metadata(message.attachment_file)
                    if metadata and "error" not in metadata:
                        message.content = json.dumps(metadata, ensure_ascii=False)
                        debug_print(f"Added metadata for image: {message.attachment_file}", component="meta")
                except Exception as e:
                    print(f"Error processing image: {e}")
                self.preview_success[ContentType.IMAGE] = self.preview_success.get(ContentType.IMAGE, 0) + 1
        
            # Process Videos
            if message.content_type.is_video and message.attachment_file:
                debug_print(f"Taking video frames for: {message.attachment_file}", component="meta")
                try:
                    frame_paths = self._take_video_frames(message.attachment_file)
                    metadata = self._get_video_metadata(message.attachment_file, frame_paths)
                    if metadata and "error" not in metadata:
                        message.content = json.dumps(metadata, ensure_ascii=False)
                        debug_print(f"Added metadata and preview for video: {message.attachment_file}", component="meta")
                except Exception as e:
                    print(f"Error taking video frames: {str(e)}", component="meta")      
                self.preview_success[ContentType.VIDEO] = self.preview_success.get(ContentType.VIDEO, 0) + 1
        
            # Process Audio
            if message.content_type.is_audio and message.attachment_file:
                debug_print(f"Processing audio: {message.attachment_file}", component="meta")
                try:
                    metadata = self._get_audio_metadata(message.attachment_file)
                    if metadata and "error" not in metadata:
                        message.content = json.dumps(metadata, ensure_ascii=False)
                        debug_print(f"Added metadata for audio: {message.attachment_file}", component="meta")
                except Exception as e:
                    print(f"Error processing audio: {e}")
                self.preview_success[ContentType.AUDIO] = self.preview_success.get(ContentType.AUDIO, 0) + 1
        
            # Process Documents
            if message.content_type.is_document and message.attachment_file:
                debug_print(f"Processing document: {message.attachment_file}", component="meta")
                try:
                    metadata = self._get_document_metadata(message.attachment_file)
                    if metadata and "error" not in metadata:
                        message.content = json.dumps(metadata, ensure_ascii=False)
                        debug_print(f"Added metadata for document: {message.attachment_file}", component="meta")
                except Exception as e:
                    print(f"Error processing document: {e}")
                self.preview_success[ContentType.DOCUMENT] = self.preview_success.get(ContentType.DOCUMENT, 0) + 1

            # Process Stickers/WebP
            if message.content_type == ContentType.STICKER and message.attachment_file:
                debug_print(f"Processing sticker: {message.attachment_file}", component="meta")
                try:
                    file_path = os.path.join(self.zip_handler.extract_path, message.attachment_file)
                    metadata = {
                        "type": "sticker",
                        "filename": message.attachment_file,
                        "format": "webp",
                        "size_bytes": os.path.getsize(file_path)
                    }
                    message.content = json.dumps(metadata, ensure_ascii=False)
                    debug_print(f"Added metadata for sticker: {message.attachment_file}", component="meta")
                except Exception as e:
                    print(f"Error processing sticker: {e}")
                self.preview_success[ContentType.STICKER] = self.preview_success.get(ContentType.STICKER, 0) + 1

            # Process Links
            if message.content_type == ContentType.LINK:
                try:
                    urls = re.findall(url_pattern, message.content)
                    if urls:
                        url = urls[0]
                        debug_print(f"Found URL: {url}", component="meta")
                        # Screenshot deaktiviert - Code bleibt für spätere Verwendung
                        '''
                        screenshot_paths = self._take_webpage_screenshot(url)
                        if screenshot_paths:
                            meta_path, report_path = screenshot_paths
                            message.content = f"{message.content}\n[Screenshot: {meta_path}]"
                            message.content += f'\n<div class="link-preview"><img src="{report_path}" alt="Screenshot of {url}" class="link-screenshot"/></div>'
                            print(f"Created screenshot for {url}")
                            self.preview_success[ContentType.LINK] = self.preview_success.get(ContentType.LINK, 0) + 1
                        else:
                            print(f"Failed to create screenshot for {url}")
                        '''
                except Exception as e:
                    print(f"Error processing URL: {e}", component="meta")
                self.preview_success[ContentType.LINK] = self.preview_success.get(ContentType.LINK, 0) + 1

        print("\n\nProcessing Summary:")
        for content_type, count in self.preview_success.items():
            print(f"  {content_type.name}: {count}")
        print(f"Processed {self.preview_success[ContentType.IMAGE]} images")
        print(f"Processed {self.preview_success[ContentType.VIDEO]} videos")
        print(f"Processed {self.preview_success[ContentType.DOCUMENT]} documents")
        print(f"Processed {self.preview_success.get(ContentType.STICKER, 0)} stickers")
        print(f"Processed {self.preview_success[ContentType.LINK]} links")

        if self.transcription_stats["transcoded"] > 0 or self.transcription_stats["errors"] > 0:
            print(f"\nAudio Processing Summary:")
            print(f"Total audio files processed: {self.preview_success[ContentType.AUDIO]}")
            print(f"- Successfully transcribed: {self.transcription_stats['transcoded']}")
            print(f"- Loaded from existing: {self.transcription_stats['loaded_existing']}")
            print(f"- Failed transcriptions: {self.transcription_stats['errors']}")

        return self.preview_success
