import re
import mimetypes
import json
import subprocess
from datetime import datetime
from typing import Optional, List, Set, Tuple
from pathlib import Path
from models import ChatMessage, ContentType
from utils import debug_print
from zip_handler import ZipHandler
from mutagen import File as MutagenFile
from webp_handler import check_webp_animation, is_valid_sticker
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import os
from bs4 import BeautifulSoup

class ChatParser:
    # Time formats in chat file:
    # Format 1 (with brackets): [08.07.22, 8:08:42 PM] Name: Message
    # Format 2 (with dash): 24.04.22, 17:53 - Name: Message
    
    # Pattern for timestamp with optional brackets and dash
    TIME_PATTERN = r'(?:\[)?(\d{2}\.\d{2}\.\d{2}),\s*(\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?)(?:\]|\s*-)'
    
    # Full message pattern with:
    # - Optional LRM character
    # - Optional brackets around timestamp
    # - Both time formats (12h/24h)
    # - Both separators (] or -)
    MESSAGE_PATTERN = r'(?:\u200E)?(?:\[)?(\d{2}\.\d{2}\.\d{2}),\s*(\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?)(?:\]|\s*-)\s*([^:]+?)\s*:\s*(.+)'
    
    # URL pattern
    URL_PATTERN = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'

    @dataclass
    class ChatStatistics:
        """Statistics about the chat messages"""
        total_messages: int = 0
        edited_messages: int = 0  # Count of edited messages
        messages_by_sender: Counter = field(default_factory=Counter)
        messages_by_type: Counter = field(default_factory=Counter)
        multiframe_count: int = 0
        missing_attachments: int = 0
        total_media_duration: float = 0  # Total duration of audio/video in seconds
        attachment_sizes: dict = field(default_factory=lambda: defaultdict(int))  # Maps ContentType to total size in bytes
        unknown_content: list = field(default_factory=list)  # List of unknown content types with their file paths
        missing_files: list = field(default_factory=list)  # List of missing attachment files
        content_types: Counter = field(default_factory=Counter)  # Zähler für alle ContentTypes
        preview_success: Counter = field(default_factory=Counter)  # Zähler für erfolgreiche Previews

        def __post_init__(self):
            pass
        
        def format_duration(self) -> str:
            """Format total media duration into hours:minutes:seconds"""
            hours = int(self.total_media_duration // 3600)
            minutes = int((self.total_media_duration % 3600) // 60)
            seconds = int(self.total_media_duration % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        def format_size(self, size_in_bytes: int) -> str:
            """Format size in bytes to human readable format"""
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_in_bytes < 1024:
                    return f"{size_in_bytes:.2f} {unit}"
                size_in_bytes /= 1024
            return f"{size_in_bytes:.2f} TB"

    def __init__(self, zip_handler: ZipHandler, device_owner: Optional[str] = None):
        self.zip_handler = zip_handler
        self.device_owner = device_owner
        self.chat_messages: List[ChatMessage] = []
        self.chat_members: Set[str] = set()
        self.statistics = self.ChatStatistics()
        # Initialize mimetypes
        mimetypes.init()

    def parse_timestamp(self, date_str: str, time_str: str) -> datetime:
        """Parse the WhatsApp timestamp format into a datetime object.
        Supports both 12-hour (8:08:42 PM) and 24-hour (17:53) formats."""
        try:
            # Remove any extra spaces in time
            time_str = ' '.join(time_str.split())
            
            # Combine date and time
            datetime_str = f"{date_str} {time_str}"
            
            # Try 24-hour format first (with or without seconds)
            try:
                if ':' in time_str:
                    if time_str.count(':') == 2:  # HH:MM:SS
                        return datetime.strptime(datetime_str, "%d.%m.%y %H:%M:%S")
                    else:  # HH:MM
                        return datetime.strptime(datetime_str, "%d.%m.%y %H:%M")
            except ValueError:
                pass
                
            # Try 12-hour format (with or without seconds)
            try:
                if 'M' in time_str:  # Contains AM/PM
                    if time_str.count(':') == 2:  # HH:MM:SS AM/PM
                        return datetime.strptime(datetime_str, "%d.%m.%y %I:%M:%S %p")
                    else:  # HH:MM AM/PM
                        return datetime.strptime(datetime_str, "%d.%m.%y %I:%M %p")
            except ValueError:
                pass
                
            # If all parsing attempts fail, raise the last ValueError
            raise ValueError(f"Could not parse timestamp: {datetime_str}")
            
        except ValueError as e:
            debug_print(f"Error parsing timestamp: {date_str} {time_str} - {str(e)}", component="chat")
            return datetime.now()  # Fallback to current time if parsing fails

    def _get_video_duration(self, file_path: str) -> Optional[float]:
        """Get video duration using ffprobe"""
        try:
            result = subprocess.run([
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                file_path
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data['format']['duration'])
                return duration
            return None
        except Exception as e:
            debug_print(f"Error getting video duration: {str(e)}", component="chat")
            return None

    def _get_media_duration(self, file_path: str) -> Optional[int]:
        """Get duration in seconds from media file"""
        try:
            # Check file extension
            ext = Path(file_path).suffix.lower()
            
            # Handle video files
            if ext in ['.mp4', '.avi', '.mov', '.webm', '.3gp']:
                duration = self._get_video_duration(file_path)
                return int(duration) if duration is not None else None
            
            # Handle audio files
            elif ext in ['.mp3', '.wav', '.ogg', '.m4a', '.opus']:
                audio = MutagenFile(file_path)
                if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                    return int(audio.info.length)
            
            return None
        except Exception as e:
            debug_print(f"Error getting media duration: {str(e)}", component="chat")
            return None

    def _check_multiframe(self, attachment_file: Optional[str], content_type: ContentType) -> bool:
        """Check if content is multiframe (e.g. GIF, Video)"""
        if not attachment_file:
            return False
        if content_type == ContentType.GIF:
            return True
        if content_type in [ContentType.VIDEO, ContentType.MP4, ContentType.VIDEO_3GP]:
            return True  # Videos are always multiframe
        return False

    def _get_content_type(self, content: str, is_attachment: bool, attachment_file: Optional[str]) -> Tuple[ContentType, bool]:
        """
        Determine content type of the message and check if it's multiframe.
        Returns a tuple of (ContentType, is_multiframe)
        
        Args:
            content: The message content
            is_attachment: Whether the message is an attachment
            attachment_file: The attachment filename if is_attachment is True
            
        Returns:
            Tuple[ContentType, bool]: The content type and whether it's multiframe
        """
        debug_print(f"\n=== Getting content type ===", component="chat")
        debug_print(f"Content: {content}", component="chat")
        debug_print(f"Is attachment: {is_attachment}", component="chat")
        debug_print(f"Attachment file: {attachment_file}", component="chat")
        
        content_type = ContentType.TEXT
        debug_info = f"content={content}, attachment={attachment_file}"
        
        # Default to TEXT for non-attachments
        if not is_attachment:
            if re.search(self.URL_PATTERN, content):
                return ContentType.LINK, False
            return ContentType.TEXT, False
        
        # Get MIME type for attachment
        mime_type = None
        exists_in_export = False
        if attachment_file:
            mime_type, _ = mimetypes.guess_type(attachment_file)
            exists_in_export = bool(self.zip_handler.find_attachment_file(attachment_file))
            debug_print(f"MIME type: {mime_type}", component="chat")
            debug_print(f"Exists in export: {exists_in_export}", component="chat")
        
        # Check for sticker files first
        sticker_marker = self._is_sticker_attachment_marker(content)
        if sticker_marker:
            attachment_file = sticker_marker
            exists_in_export = self.zip_handler.file_exists(attachment_file)
            if exists_in_export and is_valid_sticker(os.path.join(self.zip_handler.extract_path, attachment_file)):
                content_type = ContentType.STICKER
            
            if is_attachment and not exists_in_export:
                self.statistics.missing_attachments += 1
                self.statistics.missing_files.append(attachment_file)
            
            return content_type, check_webp_animation(os.path.join(self.zip_handler.extract_path, attachment_file)) if exists_in_export else False
        
        # Check for audio files first
        audio_marker = self._is_audio_attachment_marker(content)
        if audio_marker or (mime_type and mime_type.startswith('audio/')):
            # Map common audio MIME types to ContentType
            if mime_type == 'audio/mpeg' or mime_type == 'audio/mpeg3':
                content_type = ContentType.MP3
            elif mime_type == 'audio/ogg' or mime_type == 'audio/opus':
                content_type = ContentType.OGG_OPUS
            elif mime_type == 'audio/mp4' or mime_type == 'audio/m4a':
                content_type = ContentType.MP4_AUDIO
            elif mime_type == 'audio/wav':
                content_type = ContentType.WAV
            elif mime_type == 'audio/amr':
                content_type = ContentType.AMR
            else:
                # Check file extension for special cases
                if attachment_file:
                    if attachment_file.lower().endswith('.opus'):
                        content_type = ContentType.OGG_OPUS
                    elif attachment_file.lower().endswith('.m4a'):
                        content_type = ContentType.MP4_AUDIO
                    else:
                        content_type = ContentType.AUDIO  # Default to generic audio type
            
            debug_print(f"Audio file detected: {debug_info} -> {content_type}", component="chat")
            return content_type, False
        
        # First check for stickers (they are WebP files in stickers directory)
        if 'stickers' in attachment_file.lower():
            content_type = ContentType.STICKER
            
            # Track statistics
            if is_attachment and not exists_in_export:
                self.statistics.missing_attachments += 1
                self.statistics.missing_files.append(attachment_file)
            
            return content_type, check_webp_animation(os.path.join(self.zip_handler.extract_path, attachment_file)) if exists_in_export else False
            
        # Then check for image files
        image_marker = self._is_image_attachment_marker(content)
        if image_marker or (mime_type and mime_type.startswith('image/')):
            if mime_type == 'image/webp':
                if exists_in_export and is_valid_sticker(os.path.join(self.zip_handler.extract_path, attachment_file)):
                    content_type = ContentType.STICKER
                else:
                    content_type = ContentType.WEBP
            elif mime_type == 'image/gif':
                content_type = ContentType.GIF
            elif mime_type == 'image/jpeg':
                content_type = ContentType.JPEG
            elif mime_type == 'image/png':
                content_type = ContentType.PNG
            else:
                content_type = ContentType.IMAGE
            
            # Track statistics
            if is_attachment and not exists_in_export:
                self.statistics.missing_attachments += 1
                self.statistics.missing_files.append(attachment_file)
            
            return content_type, self._check_multiframe(attachment_file, content_type)
            
        # Check for video files
        video_marker = self._is_video_attachment_marker(content)
        if video_marker or (mime_type and mime_type.startswith('video/')):
            if mime_type == 'video/mp4':
                content_type = ContentType.MP4
            elif mime_type == 'video/webm':
                content_type = ContentType.WEBM
            elif mime_type == 'video/quicktime':
                content_type = ContentType.MOV
            elif mime_type == 'video/3gpp':
                content_type = ContentType.VIDEO_3GP
            else:
                content_type = ContentType.VIDEO
            
            # Track statistics
            if is_attachment and not exists_in_export:
                self.statistics.missing_attachments += 1
                self.statistics.missing_files.append(attachment_file)
            
            return content_type, True  # Videos are always multiframe
            
        # Check for documents
        doc_marker = self._is_document_attachment_marker(content)
        if doc_marker or (mime_type and mime_type.startswith(('application/', 'text/'))):
            if mime_type == 'application/pdf':
                content_type = ContentType.PDF
            elif mime_type == 'application/msword':
                content_type = ContentType.MS_WORD
            elif mime_type == 'application/vnd.ms-powerpoint':
                content_type = ContentType.MS_POWERPOINT
            elif mime_type == 'application/vnd.ms-excel':
                content_type = ContentType.MS_EXCEL
            elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                content_type = ContentType.DOCX
            elif mime_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
                content_type = ContentType.PPTX
            elif mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                content_type = ContentType.XLSX
            elif mime_type == 'text/x-vcard':
                content_type = ContentType.VCF
            else:
                content_type = ContentType.DOCUMENT
            
            # Track statistics
            if is_attachment and not exists_in_export:
                self.statistics.missing_attachments += 1
                self.statistics.missing_files.append(attachment_file)
            
            return content_type, False
            
        # If we couldn't determine the type, log it for debugging
        if mime_type:
            debug_print(f"Unknown content type: {debug_info}", component="chat")
            if is_attachment:
                self.statistics.unknown_content.append(debug_info)
                if not exists_in_export:
                    self.statistics.missing_attachments += 1
                    self.statistics.missing_files.append(attachment_file)
            
        return ContentType.UNKNOWN, False

    def _is_image_attachment_marker(self, text: str) -> str | None:
        """
        Prüft, ob der Text ein Bild-Anhang-Marker enthält und gibt diesen zurück.
        
        iOS Format: 00001008-PHOTO-2022-07-11-14-53-45.jpg (8 Ziffern-PHOTO-YYYY-MM-DD-HH-MM-SS.jpg)
        Android Format: IMG-20220518-WA0023.jpg (IMG-YYYYMMDD-WA4oder5stellige Zahl.jpg)
        
        Returns:
            str | None: Der gefundene Bild-Anhang-Marker oder None wenn keiner gefunden wurde
        """
        pattern = r'(\d{8}-PHOTO-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(jpg|jpeg|png|gif)|IMG-\d{8}-WA\d{4,5}\.(jpg|jpeg|png|gif))'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0) if match else None

    def _is_video_attachment_marker(self, text: str) -> str | None:
        """
        Prüft, ob der Text ein Video-Anhang-Marker enthält und gibt diesen zurück.
        
        iOS Format: 00001008-VIDEO-2022-07-11-14-53-45.mp4 (8 Ziffern-VIDEO-YYYY-MM-DD-HH-MM-SS.mp4)
        Android Format: VID-20220518-WA0023.mp4 (VID-YYYYMMDD-WA4oder5stellige Zahl.mp4)
        
        Returns:
            str | None: Der gefundene Video-Anhang-Marker oder None wenn keiner gefunden wurde
        """
        pattern = r'(\d{8}-VIDEO-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(mp4|mov|avi|3gp)|VID-\d{8}-WA\d{4,5}\.(mp4|mov|avi|3gp))'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0) if match else None

    def _is_audio_attachment_marker(self, text: str) -> str | None:
        """
        Prüft, ob der Text ein Audio-Anhang-Marker enthält und gibt diesen zurück.
        
        iOS Format: 00001008-AUDIO-2022-07-11-14-53-45.mp3 (8 Ziffern-AUDIO-YYYY-MM-DD-HH-MM-SS.mp3)
        Android Format: AUD-20220518-WA0023.mp3 (AUD-YYYYMMDD-WA4oder5stellige Zahl.mp3)
        PTT Format: PTT-20220518-WA0023.opus (PTT-YYYYMMDD-WA4oder5stellige Zahl.opus)
        
        Returns:
            str | None: Der gefundene Audio-Anhang-Marker oder None wenn keiner gefunden wurde
        """
        pattern = r'(\d{8}-AUDIO-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(mp3|m4a|ogg|wav)|(?:AUD|PTT)-\d{8}-WA\d{4,5}\.(mp3|m4a|ogg|wav|opus))'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0) if match else None

    def _is_document_attachment_marker(self, text: str) -> str | None:
        """
        Prüft, ob der Text ein Dokument-Anhang-Marker enthält und gibt diesen zurück.
        
        iOS Format: 00001008-DOC-2022-07-11-14-53-45.pdf (8 Ziffern-DOC-YYYY-MM-DD-HH-MM-SS.pdf)
        Android Format: DOC-20220518-WA0023.pdf (DOC-YYYYMMDD-WA4oder5stellige Zahl.pdf)
        
        Returns:
            str | None: Der gefundene Dokument-Anhang-Marker oder None wenn keiner gefunden wurde
        """
        pattern = r'(\d{8}-DOC-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(pdf|doc|docx|ppt|pptx|xls|xlsx|vcf)|DOC-\d{8}-WA\d{4,5}\.(pdf|doc|docx|ppt|pptx|xls|xlsx|vcf))'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0) if match else None

    def _is_sticker_attachment_marker(self, text: str) -> Optional[str]:
        """
        Check if the text contains a sticker attachment marker and return it.
        
        iOS Format: 00000232-STICKER-2022-07-08-23-16-44.webp (8 digits-STICKER-YYYY-MM-DD-HH-MM-SS.webp)
        Android Format: STK-20220518-WA0023.webp (STK-YYYYMMDD-WA4or5digits.webp)
        
        Returns:
            str | None: The found sticker attachment marker or None if none was found
        """
        pattern = r'(?:\d{8}-STICKER-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.webp|STK-\d{8}-WA\d{4,5}\.webp)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0) if match else None

    def parse_message_line(self, line: str) -> Optional[ChatMessage]:
        """Parse a single line from the chat file into a ChatMessage object"""
        try:
            debug_print(f"\n=== Parsing message line ===", component="chat")
            debug_print(f"Line: {line}", component="chat")
            
            # Skip empty lines
            if not line.strip():
                debug_print("Skipping empty line", component="chat")
                return None

            # Try to match the full message pattern
            match = re.match(self.MESSAGE_PATTERN, line)
            if not match:
                debug_print("No message pattern match", component="chat")
                return None

            date_str, time_str, sender, content = match.groups()
            debug_print(f"Extracted: date={date_str}, time={time_str}, sender={sender}, content={content}", component="chat")
            
            # Add sender to chat members
            self.chat_members.add(sender)
            
            # Check if message was edited
            is_edited = False
            edited_marker = " ‎<Diese Nachricht wurde bearbeitet.>"
            if content.endswith(edited_marker):
                is_edited = True
                content = content[:-len(edited_marker)].rstrip()
                debug_print("Message is edited", component="chat")
            
            # Initialize attachment variables
            is_attachment = False
            attachment_file = None
            
            # Try to extract attachment filename if present
            try:
                if content:
                    # First check for the <Anhang: filename> pattern
                    attachment_match = re.match(r'‎?<Anhang:\s*([^>]+)>', content)
                    if attachment_match:
                        attachment_file = attachment_match.group(1)
                        is_attachment = True
                        debug_print(f"Found attachment marker: {attachment_file}", component="chat")
                    else:
                        # Check for Android attachment format
                        android_match = re.match(r'‎?([^\s]+)\s*\(Datei angehängt\)', content)
                        if android_match:
                            attachment_file = android_match.group(1)
                            is_attachment = True
                            debug_print(f"Found Android attachment: {attachment_file}", component="chat")
                        else:
                            # Check if the content matches our other attachment patterns
                            attachment_file = (
                                self._is_image_attachment_marker(content) or
                                self._is_video_attachment_marker(content) or
                                self._is_audio_attachment_marker(content) or
                                self._is_document_attachment_marker(content) or
                                self._is_sticker_attachment_marker(content)
                            )
                            if attachment_file:
                                is_attachment = True
                                debug_print(f"Found attachment pattern: {attachment_file}", component="chat")
            except ValueError as e:
                debug_print(f"Error extracting attachment: {e}", component="chat")
            
            # Get content information
            content_length = self._extract_content_length(content, is_attachment, attachment_file)
            content_type, is_multiframe = self._get_content_type(content, is_attachment, attachment_file)
            debug_print(f"Content type: {content_type}, Multiframe: {is_multiframe}", component="chat")
            
            # Update statistics
            self.statistics.total_messages += 1
            self.statistics.messages_by_sender[sender] += 1
            self.statistics.messages_by_type[content_type] += 1
            
            # Track multiframe content
            if is_multiframe:
                self.statistics.multiframe_count += 1
            
            # Track attachments
            if is_attachment:
                exists_in_export = bool(self.zip_handler.find_attachment_file(attachment_file))
                if not exists_in_export:
                    self.statistics.missing_attachments += 1
                    self.statistics.missing_files.append(attachment_file)
                else:
                    # Get file size
                    file_path = self.zip_handler.find_attachment_file(attachment_file)
                    if file_path:
                        try:
                            size = os.path.getsize(file_path)
                            self.statistics.attachment_sizes[content_type] += size
                        except OSError:
                            debug_print(f"Error getting file size: {file_path}", component="chat")
                    
                    # Get media duration for audio/video
                    if content_type.is_audio or content_type.is_video:
                        duration = self._get_media_duration(file_path)
                        if duration:
                            self.statistics.total_media_duration += duration
            
            if is_edited:
                self.statistics.edited_messages += 1
                debug_print("Incrementing edited messages count", component="chat")
            
            message = ChatMessage(
                timestamp=self.parse_timestamp(date_str, time_str),
                sender=sender,
                content=content,
                content_type=content_type,
                content_length=content_length,
                is_attachment=is_attachment,
                attachment_file=attachment_file,
                exists_in_export=attachment_file is not None and self.zip_handler.find_attachment_file(attachment_file) is not None,
                is_multiframe=is_multiframe,
                is_edited=is_edited
            )
            
            debug_print(f"Created message object: sender={message.sender}, type={message.content_type}, edited={message.is_edited}", component="chat")
            return message

        except Exception as e:
            debug_print(f"Error parsing message line: {str(e)}", component="chat")
            if DEBUG:
                import traceback
                traceback.print_exc()
            return None

    def parse_chat_file(self) -> List[ChatMessage]:
        """Parse the entire chat file and return a list of ChatMessage objects"""
        chat_file = self.zip_handler.find_chat_file()
        if not chat_file:
            debug_print("Chat file not found", component="chat")
            return []

        try:
            with open(chat_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            total_lines = len(lines)
            print(f"\nParsing {total_lines} lines from chat file...")
            
            for i, line in enumerate(lines, 1):
                message = self.parse_message_line(line)
                if message:
                    self.chat_messages.append(message)
                
                # Print progress every 1000 lines or at the end
                if i % 1000 == 0 or i == total_lines:
                    progress = (i / total_lines) * 100
                    print(f"Progress: {progress:.1f}% ({i}/{total_lines} lines)", end='\r')

            print(f"\nFinished parsing {len(self.chat_messages)} messages from {total_lines} lines")
            #self.print_statistics()
            return self.chat_messages

        except Exception as e:
            debug_print(f"Error parsing chat file: {str(e)}", component="chat")
            return []

    def get_statistics(self) -> ChatStatistics:
        """Get chat statistics"""
        return self.statistics

    def print_statistics(self):
        """Print chat statistics to stdout"""
        print("\nChat Statistics:")
        total_messages = len(self.chat_messages)
        if total_messages == 0:
            print("Error: No messages found in chat file")
            return
            
        print(f"Total Messages: {total_messages}")
        
        # Zähle die verschiedenen Nachrichtentypen
        content_types = Counter()
        edited_messages = 0
        attachments = 0
        attachment_types = Counter()
        
        for msg in self.chat_messages:
            content_types[msg.content_type] += 1
            if msg.is_edited:
                edited_messages += 1
            if msg.is_attachment:
                attachments += 1
                if msg.attachment_type:
                    attachment_types[msg.attachment_type] += 1
        
        print(f"Edited Messages: {edited_messages}")
        print(f"Total Attachments: {attachments}")
        
        if content_types:
            print("\nContent Type Statistics:")
            for content_type, count in content_types.most_common():
                success = self.statistics.preview_success.get(content_type, 0)
                print(f"  {content_type.name}: {count}", end='')
                if content_type in [ContentType.VIDEO, ContentType.LINK]:
                    success_rate = (success/count)*100 if count > 0 else 0
                    print(f" (Previews: {success}, Success Rate: {success_rate:.1f}%)")
                else:
                    print()
        
        if attachment_types:
            print("\nAttachment Types:")
            for type_name, count in attachment_types.most_common():
                print(f"  {type_name}: {count}")

    def _extract_content_length(self, content: str, is_attachment: bool, attachment_file: Optional[str]) -> Optional[int]:
        """Extract content length based on message type"""
        if not is_attachment:
            # For text messages, return character count
            return len(content)
        
        if not attachment_file or not self.zip_handler.extract_path:
            return None
            
        # Get full path to attachment
        file_path = self.zip_handler.find_attachment_file(attachment_file)
        if not file_path:
            return None
            
        # Get duration for media files
        return self._get_media_duration(file_path)

    def _take_video_frames(self, content: str, video_file: str) -> Optional[Tuple[str, str]]:
        """
        Extrahiert 4 Frames aus einem Video (bei 20%, 40%, 60% und 80% der Gesamtlänge)
        und fügt sie zu einem Vorschaubild zusammen.
        
        Args:
            content: Der Nachrichteninhalt
            video_file: Der Dateiname des Videos
            
        Returns:
            Tuple[str, str]: (Relativer Pfad zum Bild im Meta-Dir, Relativer Pfad im Report) oder None bei Fehler
        """
        try:
            import cv2
            import numpy as np
            from PIL import Image
            import hashlib
            import shutil
            
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
                    print(f"Error: Could not read frame at position {pos}")
            
            cap.release()
            
            if len(frames) != 4:
                print(f"Error: Could not extract all frames from {video_file}")
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
            print(f"Error extracting video frames: {e}")
            return None
