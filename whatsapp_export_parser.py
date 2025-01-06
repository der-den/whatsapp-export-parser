import os
import re
import sys
import shutil
import zipfile
import hashlib
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

# PDF generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import inch

# Image handling
from PIL import Image as PILImage

# Emoji support
import emoji


def debug_print(message):
    """Print debug messages if DEBUG is True"""
    if WhatsAppExportParser.DEBUG:
        print(f"[DEBUG] {message}")


def debug_attachment_print(message):
    """Print debug messages for attachments if DEBUG_ATTACHMENTS is True"""
    if WhatsAppExportParser.DEBUG_ATTACHMENTS:
        print(f"[DEBUG ATTACHMENT] {message}")


@dataclass
class ChatMessage:
    """Represents a single chat message"""
    timestamp: datetime
    sender: str
    content: str
    is_attachment: bool
    attachment_file: Optional[str] = None
    exists_in_export: bool = False  # Whether the attachment exists in the export

class WhatsAppExportParser:
    DEBUG = False  # General debug output
    DEBUG_ATTACHMENTS = False  # Debug output for attachments and media
    
    # Time format in chat file: [08.07.22, 8:08:42 PM]
    TIME_PATTERN = r'\[(\d{2}\.\d{2}\.\d{2}),\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M)\]'
    # Full message pattern with optional LRM character
    MESSAGE_PATTERN = r'(?:\u200E)?\[(\d{2}\.\d{2}\.\d{2}),\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M)\]\s*([^:]+?)\s*:\s*(.+)'
    # Attachment patterns for different languages
    #ATTACHMENT_PATTERNS = [
        # WhatsApp standard format with numbering
    #    r'\u200E?<(?:Anhang|attachment|attached|file):\s*(\d+-(?:AUDIO|VIDEO|PHOTO|IMAGE|DOC|DOCUMENT)-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.[a-zA-Z0-9]+)>',
        
        # General file pattern with common extensions
    #    r'\u200E?<[^<>:]*\.(?:jpg|jpeg|png|gif|mp4|webp|opus|pdf|mp3|wav|doc|docx)(?:\s|$)'  # File extensions
    #]

    def __init__(self, zip_file_path, device_owner=None):
        self.zip_file_path = str(Path(zip_file_path).resolve())
        self.device_owner = device_owner
        self.chat_messages: List[ChatMessage] = []
        self.media_files = []
        self.media_info = []
        self.extract_path = None
        self.chat_members = set()  # Store all unique chat members
        
        debug_print(f"Initialized parser with:")
        debug_print(f"  ZIP file: {self.zip_file_path}")
        debug_print(f"  Device owner: {device_owner}")

    def calculate_md5(self):
        """Calculate MD5 hash of the ZIP file"""
        try:
            md5_hash = hashlib.md5()
            with open(self.zip_file_path, "rb") as f:
                # Read the file in chunks to handle large files
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception as e:
            debug_print(f"Error calculating MD5: {str(e)}")
            return "N/A"

    def calculate_file_md5(self, file_path):
        """Calculate MD5 hash of a file"""
        try:
            md5_hash = hashlib.md5()
            with open(file_path, "rb") as f:
                # Read the file in chunks to handle large files
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception as e:
            debug_print(f"Error calculating MD5 for file: {str(e)}")
            return "N/A"

    def format_size(self, size_bytes):
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def unpack_zip(self):
        md5_hash = self.calculate_md5()
        # Create extraction path in the same directory as the input ZIP
        self.extract_path = str(Path(self.zip_file_path).parent / md5_hash)
        debug_print(f"Extracting ZIP to: {self.extract_path}")
        os.makedirs(self.extract_path, exist_ok=True)
        with zipfile.ZipFile(self.zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(self.extract_path)
        debug_print("ZIP extraction complete")

    def parse_timestamp(self, date_str: str, time_str: str) -> datetime:
        """Parse the WhatsApp timestamp format into a datetime object"""
        try:
            # Remove any extra spaces in time
            time_str = ' '.join(time_str.split())
            # Combine date and time
            datetime_str = f"{date_str} {time_str}"
            # Parse the datetime
            dt = datetime.strptime(datetime_str, "%d.%m.%y %I:%M:%S %p")
            return dt
        except ValueError as e:
            debug_print(f"Error parsing timestamp: {date_str} {time_str} - {str(e)}")
            return datetime.now()  # Fallback to current time if parsing fails

    def parse_message_line(self, line: str) -> Optional[ChatMessage]:
        """Parse a single line from the chat file into a ChatMessage object"""
        try:
            # Skip empty lines
            if not line.strip():
                return None

            debug_print(f"Parsing line: {line}")
            
            # Try to match the full message pattern
            match = re.match(self.MESSAGE_PATTERN, line)  # Don't strip here
            if not match:
                debug_print("  No match found for line")
                return None

            date_str, time_str, sender, content = match.groups()
            
            # Ensure proper encoding of special characters
            sender = sender.encode('utf-8').decode('utf-8')
            content = content.encode('utf-8').decode('utf-8')
            
            # Convert emoji to their text representation for better PDF support
            try:
                content = self.process_emojis(content)
                debug_print(f"Processed content with emojis: {content}")
            except Exception as e:
                debug_print(f"Error converting emoji: {str(e)}")
            
            timestamp = self.parse_timestamp(date_str, time_str)
            
            # Check if the message contains an attachment
            is_attachment = False
            attachment_file = None
            exists_in_export = False
            
            # Try to find attachment markers
            if '‎<' in content or '<' in content:
                try:
                    # Try to find the colon after Anhang/attachment
                    if ':' in content:
                        start_idx = content.rindex(':') + 1
                        # Find the next > after the colon
                        remaining = content[start_idx:]
                        if '>' in remaining:
                            end_idx = start_idx + remaining.index('>')
                            attachment_file = content[start_idx:end_idx].strip()
                            
                            # Check if the file exists in the extracted directory
                            if self.extract_path:
                                file_path = self.find_attachment_file(attachment_file)
                                if file_path:
                                    is_attachment = True
                                    exists_in_export = True
                                    if file_path not in self.media_files:
                                        self.media_files.append(file_path)
                                else:
                                    is_attachment = True
                                    exists_in_export = False
                                    debug_print(f"Attachment not found in export: {attachment_file}")
                except ValueError as e:
                    debug_print(f"Error extracting attachment: {e}")
            
            debug_print(f"  Raw content: {repr(content)}")
            debug_print(f"  Is attachment: {is_attachment}")
            if is_attachment:
                debug_print(f"  Attachment file: {repr(attachment_file)}")
                debug_print(f"  Exists in export: {exists_in_export}")

            # Now we can safely strip the content
            content = content.strip()
            
            message = ChatMessage(
                timestamp=timestamp,
                sender=sender.strip(),
                content=content,
                is_attachment=is_attachment,
                attachment_file=attachment_file,
                exists_in_export=exists_in_export
            )
            
            return message
            
        except Exception as e:
            debug_print(f"Error parsing line: {str(e)}")
            return None

    def find_attachment_file(self, filename):
        """Find the actual file path for an attachment in the extracted directory"""
        debug_attachment_print(f"Looking for attachment: {filename}")
        
        # First try exact match
        for root, _, files in os.walk(self.extract_path):
            if filename in files:
                file_path = os.path.join(root, filename)
                debug_attachment_print(f"Found exact match: {file_path}")
                return file_path
                
        # Try case-insensitive match
        filename_lower = filename.lower()
        for root, _, files in os.walk(self.extract_path):
            for file in files:
                if file.lower() == filename_lower:
                    file_path = os.path.join(root, file)
                    debug_attachment_print(f"Found case-insensitive match: {file_path}")
                    return file_path
                    
        # Try matching without special characters
        clean_filename = re.sub(r'[^a-zA-Z0-9.]', '', filename)
        for root, _, files in os.walk(self.extract_path):
            for file in files:
                clean_file = re.sub(r'[^a-zA-Z0-9.]', '', file)
                if clean_file == clean_filename:
                    file_path = os.path.join(root, file)
                    debug_attachment_print(f"Found match without special chars: {file_path}")
                    return file_path
        
        debug_attachment_print(f"No matching file found for: {filename}")
        return None

    def parse_chats(self):
        """Parse the chat file into structured message objects"""
        try:
            # Find the chat file
            chat_files = [f for f in os.listdir(self.extract_path) 
                         if f.endswith('.txt') and not f.startswith('._')]
            
            if not chat_files:
                raise Exception("No chat file found in ZIP")
            
            chat_file = os.path.join(self.extract_path, chat_files[0])
            debug_print(f"Found chat file: {chat_file}")
            
            # Read and parse the chat file
            with open(chat_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Process each line
            for line in lines:
                message = self.parse_message_line(line)
                if message:
                    self.chat_messages.append(message)
            
            # Show statistics
            attachments = sum(1 for msg in self.chat_messages if msg.is_attachment)
            unique_senders = len(set(msg.sender for msg in self.chat_messages))
            first_date = self.chat_messages[0].timestamp.strftime('%d.%m.%Y') if self.chat_messages else 'N/A'
            last_date = self.chat_messages[-1].timestamp.strftime('%d.%m.%Y') if self.chat_messages else 'N/A'
            
            print("\nChat Statistics:")
            print(f"- Time period: {first_date} to {last_date}")
            print(f"- Total messages: {len(self.chat_messages):,}")
            print(f"- Participants: {unique_senders}")
            print(f"- Messages with attachments: {attachments:,}")
            missing_attachments = sum(1 for msg in self.chat_messages 
                                    if msg.is_attachment and not msg.exists_in_export)
            print(f"- Messages with attachments not in export: {missing_attachments:,}")
            
            return True
            
        except Exception as e:
            print(f"\nError parsing chat file: {str(e)}")
            return False

    def scan_chat_members(self):
        """Scan the chat file to find all unique members"""
        try:
            chat_files = [f for f in os.listdir(self.extract_path) 
                         if f.endswith('.txt') and not f.startswith('._')]
            
            if not chat_files:
                return False
                
            chat_file = os.path.join(self.extract_path, chat_files[0])
            
            with open(chat_file, 'r', encoding='utf-8') as f:
                for line in f:
                    match = re.match(self.MESSAGE_PATTERN, line)
                    if match:
                        sender = match.group(3).strip()
                        self.chat_members.add(sender)
            
            if not self.device_owner and len(self.chat_members) > 0:
                # Try to guess device owner - usually the one who appears most
                sender_counts = {}
                for msg in self.chat_messages:
                    sender_counts[msg.sender] = sender_counts.get(msg.sender, 0) + 1
                self.device_owner = max(sender_counts.items(), key=lambda x: x[1])[0]
                print(f"- Auto-detected device owner as: {self.device_owner}")
            
            return True
        except Exception as e:
            debug_print(f"Error scanning chat members: {str(e)}")
            return False

    def check_media_files(self):
        """Scan for media files and gather information about them"""
        debug_attachment_print("\nScanning for media files...")
        media_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.pdf', '.ogg', '.opus']
        
        # First check files referenced in chat messages
        for message in self.chat_messages:
            if message.is_attachment and message.attachment_file:
                debug_attachment_print(f"Processing attachment from message: {message.attachment_file}")
                
                # Find the file in the extract path
                for root, _, files in os.walk(self.extract_path):
                    if message.attachment_file in files:
                        file_path = os.path.join(root, message.attachment_file)
                        if file_path not in self.media_files:
                            self.media_files.append(file_path)
                            debug_attachment_print(f"  Found referenced file: {file_path}")
                        break
        
        # Then scan for any additional media files
        for root, _, files in os.walk(self.extract_path):
            for file in files:
                if any(file.lower().endswith(ext) for ext in media_extensions):
                    file_path = os.path.join(root, file)
                    if file_path not in self.media_files:
                        self.media_files.append(file_path)
                        debug_attachment_print(f"Found additional media file: {file}")
        
        # Gather information about all media files
        for file_path in self.media_files:
            try:
                file_name = os.path.basename(file_path)
                file_size = os.path.getsize(file_path) / 1024  # Size in KB
                md5_hash = self.calculate_file_md5(file_path)
                duration = self.get_media_duration(file_path)
                
                debug_attachment_print(f"\nMedia file details:")
                debug_attachment_print(f"  Name: {file_name}")
                debug_attachment_print(f"  Path: {file_path}")
                debug_attachment_print(f"  Size: {self.format_size(file_size)}")
                debug_attachment_print(f"  MD5: {md5_hash}")
                debug_attachment_print(f"  Duration: {duration}")
                
                self.media_info.append({
                    'name': file_name,
                    'path': file_path,
                    'md5': md5_hash,
                    'size': self.format_size(file_size),
                    'duration': duration
                })
            except Exception as e:
                debug_attachment_print(f"Error processing media file {file_path}: {str(e)}")
                continue
        
        debug_attachment_print(f"\nFound {len(self.media_files)} media files in total")

    def get_media_duration(self, file_path):
        debug_attachment_print(f"Getting duration for: {file_path}")
        try:
            if file_path.lower().endswith('.mp4'):
                audio = MP4(file_path)
            elif file_path.lower().endswith('.ogg'):
                audio = OggVorbis(file_path)
            else:
                return "N/A"
            
            if audio.info.length:
                minutes = int(audio.info.length // 60)
                seconds = int(audio.info.length % 60)
                duration = f"{minutes:02d}:{seconds:02d}"
                debug_attachment_print(f"  Duration: {duration}")
                return duration
            return "N/A"
        except Exception as e:
            debug_attachment_print(f"  Error getting duration: {str(e)}")
            return "N/A"

    def generate_media_pdf(self, output_dir):
        # Use the same directory as the main PDF
        media_pdf_path = str(Path(output_dir) / "Media Files.pdf")
        debug_attachment_print(f"Generating media PDF: {media_pdf_path}")
        
        # Create the document with better margins
        doc = SimpleDocTemplate(
            media_pdf_path,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        # Create a list to store page numbers
        page_numbers = []
        
        def add_page_number(canvas, doc):
            canvas.saveState()
            page_numbers.append(canvas.getPageNumber())
            canvas.setFont('Helvetica', 8)
            page_num = canvas.getPageNumber()
            # Use the current highest page number as total
            text = f"Page {page_num} of {max(page_numbers)}"
            canvas.drawRightString(doc.pagesize[0] - 0.5*inch, 0.25*inch, text)
            canvas.restoreState()
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=10,
            spaceBefore=10,
            alignment=1,  # Center alignment
            textColor=colors.HexColor('#2c3e50')  # Dark blue-gray
        )
        
        info_style = ParagraphStyle(
            'InfoStyle',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=20,
            alignment=1,  # Center alignment
            textColor=colors.HexColor('#34495e')  # Lighter blue-gray
        )
        
        # Add title and ZIP information
        elements.append(Paragraph("WhatsApp Export Media Files Report", title_style))
        
        zip_name = os.path.basename(self.zip_file_path)
        zip_hash = self.calculate_md5()
        zip_size = os.path.getsize(self.zip_file_path) / 1024  # Size in KB
        zip_info = f"ZIP File: {zip_name}<br/>Size: {self.format_size(zip_size)}<br/>MD5 Hash: {zip_hash}"
        elements.append(Paragraph(zip_info, info_style))
        
        # Add some space
        elements.append(Spacer(1, 20))
        
        # Create the table data
        table_data = [['Filename', 'MD5 Hash', 'Size', 'Duration']]
        for info in self.media_info:
            # Truncate filename if too long
            filename = info['name']
            if len(filename) > 40:
                filename = filename[:37] + "..."
            
            table_data.append([
                filename,
                info['md5'],
                info['size'],
                info['duration']
            ])
        
        # Create table style with modern colors
        style = TableStyle([
            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),  # Reduced font size
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Content style
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),  # Reduced font size
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            
            # Grid style
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2c3e50')),
            
            # Alternate row colors
            *[('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f5f6fa'))
              for i in range(2, len(table_data), 2)],
            
            # Word wrap
            ('WORDWRAP', (0, 0), (-1, -1), True),
        ])
        
        # Create the table with adjusted column widths
        available_width = doc.width
        col_widths = [
            available_width * 0.35,  # Filename (35%)
            available_width * 0.40,  # MD5 Hash (40%)
            available_width * 0.125, # Size (12.5%)
            available_width * 0.125  # Duration (12.5%)
        ]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(style)
        
        elements.append(table)
        
        # Build the PDF with page numbers
        doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)

    def find_font(self, font_name):
        """Find a font file in common system locations"""
        common_paths = [
            '/usr/share/fonts/noto',      # Arch Linux
            '/usr/share/fonts/TTF',       # Some Linux
            '/usr/local/share/fonts',     # Unix-like
            '/usr/share/fonts/truetype',  # Debian/Ubuntu
            '/usr/share/fonts/truetype/noto',  # Ubuntu Noto location
            '/usr/share/fonts/dejavu',    # DejaVu location
            os.path.expanduser('~/.fonts'),  # User fonts
            os.path.expanduser('~/.local/share/fonts')  # User fonts
        ]
        
        debug_print(f"Searching for font: {font_name}")
        for path in common_paths:
            debug_print(f"Checking directory: {path}")
            if os.path.exists(path):
                files = os.listdir(path)
                for file in files:
                    # More flexible matching for font names
                    file_lower = file.lower()
                    if (font_name.lower() in file_lower and 
                        file_lower.endswith('.ttf') and
                        not file_lower.endswith('bold.ttf') and
                        not file_lower.endswith('italic.ttf')):
                        full_path = os.path.join(path, file)
                        debug_print(f"Found matching font: {full_path}")
                        return full_path
        debug_print(f"Font not found: {font_name}")
        return None

    def setup_pdf_fonts(self):
        """Setup fonts for PDF generation with proper Unicode and emoji support"""
        try:
            # Find and register Noto Sans for regular text
            regular_font = self.find_font('NotoSans')  # Try to find NotoSans
            if regular_font:
                font_name = 'NotoSans'
                pdfmetrics.registerFont(TTFont(font_name, regular_font))
                debug_print(f"Found and registered font: {regular_font}")
                return font_name
            else:
                debug_print("No suitable font found")
                return 'Helvetica'
            
        except Exception as e:
            debug_print(f"Error setting up fonts: {str(e)}")
            return 'Helvetica'

    def generate_pdf(self, output_path):
        """Generate a PDF file from the parsed chat messages"""
        try:
            print(f"\nGenerating PDF: {os.path.basename(output_path)}")
            
            # Setup Unicode font
            font_name = self.setup_pdf_fonts()
            print(f"Using font: {font_name}")
            
            # Create the document with Unicode support
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=30,
                encoding='utf-8'
            )
            
            # Get the default style sheet and create custom styles
            print("Setting up document styles...")
            styles = getSampleStyleSheet()
            
            # Create custom chat styles to the stylesheet
            styles.add(ParagraphStyle(
                'ChatLeft',
                parent=styles['Normal'],
                fontName=font_name,  # Use NotoSans as primary font
                fontSize=10,
                spaceAfter=8,
                leading=14,
                alignment=0,  # Left align
                backColor='#f0f0f0',  # Light gray background
                borderColor='#e0e0e0',
                borderWidth=1,
                borderPadding=5,
                bulletIndent=0,
                leftIndent=0,
                encoding='utf-8'
            ))
            
            styles.add(ParagraphStyle(
                'ChatRight',
                parent=styles['Normal'],
                fontName=font_name,  # Use NotoSans as primary font
                fontSize=10,
                spaceAfter=8,
                leading=14,
                alignment=2,  # Right align
                backColor='#dcf8c6',  # WhatsApp green
                borderColor='#c7e7b5',
                borderWidth=1,
                borderPadding=5,
                bulletIndent=0,
                rightIndent=0,
                encoding='utf-8'
            ))
            
            # Build PDF content
            elements = []
            
            # Add title
            print("Adding document header...")
            elements.append(Paragraph("WhatsApp Chat Export", styles['Title']))
            
            # Add file info
            zip_info = self.get_zip_info()
            if zip_info:
                elements.append(Paragraph(f"File: {zip_info['name']}", styles['Normal']))
                elements.append(Paragraph(f"Size: {zip_info['size']}", styles['Normal']))
                elements.append(Paragraph(f"Date: {zip_info['date']}", styles['Normal']))
                elements.append(Paragraph(f"MD5: {zip_info['md5']}", styles['Normal']))
                elements.append(Spacer(1, 20))
            
            # Add chat statistics
            if self.chat_messages:
                print("Calculating chat statistics...")
                first_msg = self.chat_messages[0]
                last_msg = self.chat_messages[-1]
                unique_senders = len(set(msg.sender for msg in self.chat_messages))
                attachment_count = sum(1 for msg in self.chat_messages if msg.is_attachment)
                
                elements.append(Paragraph("Chat Statistics:", styles['Normal']))
                elements.append(Paragraph(f"Messages: {len(self.chat_messages):,}", styles['Normal']))
                elements.append(Paragraph(f"Participants: {unique_senders}", styles['Normal']))
                elements.append(Paragraph(f"Attachments: {attachment_count:,}", styles['Normal']))
                elements.append(Paragraph(
                    f"Date Range: {first_msg.timestamp.strftime('%d.%m.%Y')} - {last_msg.timestamp.strftime('%d.%m.%Y')}", 
                    styles['Normal']
                ))
                elements.append(Spacer(1, 20))
            
            # Process messages
            print("\nProcessing messages...")
            total_msgs = len(self.chat_messages)
            for i, message in enumerate(self.chat_messages, 1):
                if i % 100 == 0:  # Show progress every 100 messages
                    progress = (i / total_msgs) * 100
                    print(f"\rProgress: {progress:.1f}% ({i:,}/{total_msgs:,} messages)", end='', flush=True)
                
                # Determine if this is the device owner's message
                is_owner = message.sender == self.device_owner
                style = styles['ChatLeft' if is_owner else 'ChatRight']  # Reversed to put owner on left
                
                # Add sender name
                datetime_str = message.timestamp.strftime("%d.%m.%y, %H:%M")
                elements.append(Paragraph(f"{message.sender} [{datetime_str}]", style))
                
                # Handle image attachments
                if message.is_attachment and message.exists_in_export:
                    attachment_file = None
                    if ':' in message.content:
                        # Extract filename after the colon
                        start_idx = message.content.rindex(':') + 1
                        # Find the next > after the colon
                        remaining = message.content[start_idx:]
                        if '>' in remaining:
                            end_idx = start_idx + remaining.index('>')
                            attachment_file = message.content[start_idx:end_idx].strip()
                    else:
                        # Try to extract filename between < and >
                        match = re.search(r'<([^>]+)>', message.content)
                        if match:
                            attachment_file = match.group(1).strip()
                    
                    if attachment_file:
                        file_path = self.find_attachment_file(attachment_file)
                        if file_path and self.is_image_file(file_path):
                            debug_attachment_print(f"Processing image: {file_path}")
                            self.process_image_message(message, file_path, elements, styles)
                            continue
                
                # Add message content
                elements.append(Paragraph(message.content, style))
                elements.append(Spacer(1, 5))
            
            print("\rProgress: 100% - Complete!")
            
            # Build the PDF
            print("\nGenerating final PDF document...")
            doc.build(elements)
            print(f"PDF generated successfully: {os.path.basename(output_path)}")
            
        except Exception as e:
            print(f"\nError generating PDF: {str(e)}")
            if self.DEBUG:
                import traceback
                traceback.print_exc()
        finally:
            # Cleanup
            if hasattr(self, 'extract_path') and self.extract_path and os.path.exists(self.extract_path):
                try:
                    print(f"\nCleaning up temporary directory: {self.extract_path}")
                    shutil.rmtree(self.extract_path)
                    print("Cleanup complete")
                except Exception as e:
                    print(f"Error during cleanup: {str(e)}")
                    print(f"Warning: Could not clean up temporary directory: {self.extract_path}")

    def get_zip_info(self):
        """Get information about the ZIP file"""
        try:
            zip_size = os.path.getsize(self.zip_file_path) / 1024  # Size in KB
            zip_name = os.path.basename(self.zip_file_path)
            zip_date = datetime.fromtimestamp(os.path.getmtime(self.zip_file_path))
            
            return {
                'name': zip_name,
                'size': self.format_size(zip_size),
                'date': zip_date.strftime('%d.%m.%Y %H:%M:%S'),
                'md5': self.calculate_md5()
            }
        except Exception as e:
            debug_print(f"Error getting ZIP info: {str(e)}")
            return None

    def is_image_file(self, filename):
        """Check if a file is an image based on extension"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        return Path(filename).suffix.lower() in image_extensions

    def get_image_info(self, image_path):
        """Get image information (dimensions, size, and MD5)"""
        try:
            img = PILImage.open(image_path)
            img_width, img_height = img.size
            file_size = os.path.getsize(image_path)
            
            # Calculate MD5 hash
            md5_hash = hashlib.md5()
            with open(image_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    md5_hash.update(chunk)
            
            return {
                'name': os.path.basename(image_path),
                'width': img_width,
                'height': img_height,
                'size': self.format_size(file_size / 1024),  # Convert to KB
                'md5': md5_hash.hexdigest()
            }
        except Exception as e:
            debug_print(f"Error getting image info: {str(e)}")
            return None
        
    def add_image_to_pdf(self, image_path, max_width=400, max_height=300):
        """Add an image to the PDF with maximum dimensions while preserving aspect ratio"""
        try:
            # Get image info
            info = self.get_image_info(image_path)
            if not info:
                return None, None
                
            # Calculate scaling to fit within max dimensions while preserving aspect ratio
            width_ratio = max_width / info['width'] if info['width'] > max_width else 1
            height_ratio = max_height / info['height'] if info['height'] > max_height else 1
            scale = min(width_ratio, height_ratio)
            
            # Calculate new dimensions
            new_width = int(info['width'] * scale)
            new_height = int(info['height'] * scale)
            
            # Create reportlab image
            img = Image(image_path, width=new_width, height=new_height)
            
            # Create image caption with size info
            caption = f"Image: {info['width']}x{info['height']} pixels, {info['size']}"
            
            return img, caption
        except Exception as e:
            debug_print(f"Error adding image {image_path}: {str(e)}")
            return None, None

    def get_attachment_stats(self):
        """Get statistics about attachments in the ZIP file"""
        stats = {
            'images': {'count': 0, 'size': 0, 'extensions': set()},
            'audio': {'count': 0, 'size': 0, 'extensions': set()},
            'video': {'count': 0, 'size': 0, 'extensions': set()},
            'documents': {'count': 0, 'size': 0, 'extensions': set()},
            'other': {'count': 0, 'size': 0, 'extensions': set()},
            'total_size': 0
        }
        
        # Group files by type
        for root, _, files in os.walk(self.extract_path):
            for file in files:
                if file.startswith('._') or file.endswith('.txt'):  # Skip metadata files and chat log
                    continue
                    
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)
                ext = Path(file).suffix.lower()
                
                # Update total size
                stats['total_size'] += file_size
                
                # Categorize file
                if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
                    category = 'images'
                elif ext in {'.mp3', '.wav', '.ogg', '.opus', '.m4a'}:
                    category = 'audio'
                elif ext in {'.mp4', '.avi', '.mov', '.webm'}:
                    category = 'video'
                elif ext in {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt'}:
                    category = 'documents'
                else:
                    category = 'other'
                
                stats[category]['count'] += 1
                stats[category]['size'] += file_size
                stats[category]['extensions'].add(ext)
        
        return stats

    def print_attachment_stats(self):
        """Print statistics about attachments found in the ZIP file"""
        stats = self.get_attachment_stats()
        
        print("\nAttachment Statistics:")
        print("---------------------")
        
        # Print each category
        categories = [
            ('Images', 'images'),
            ('Audio Files', 'audio'),
            ('Videos', 'video'),
            ('Documents', 'documents'),
            ('Other Files', 'other')
        ]
        
        for display_name, key in categories:
            if stats[key]['count'] > 0:
                print(f"\n{display_name}:")
                print(f"  Count: {stats[key]['count']:,}")
                print(f"  Total Size: {self.format_size(stats[key]['size'])}")
                print(f"  Types: {', '.join(sorted(stats[key]['extensions']))}")
        
        # Count messages with missing attachments
        total_attachments = sum(1 for msg in self.chat_messages if msg.is_attachment)
        missing_attachments = sum(1 for msg in self.chat_messages 
                                if msg.is_attachment and not msg.exists_in_export)
        found_attachments = total_attachments - missing_attachments
        
        # Print totals
        print(f"\nAttachment Messages:")
        print(f"  Total Referenced: {total_attachments:,}")
        print(f"  Found in Export: {found_attachments:,}")
        print(f"  Missing from Export: {missing_attachments:,}")
        
        print(f"\nTotal Files in Export: {sum(stats[key]['count'] for key in stats if key != 'total_size'):,}")
        print(f"Total Size: {self.format_size(stats['total_size'])}")

    def format_image_metadata(self, img_info, align_right=False):
        """Format image metadata in a table"""
        if not img_info:
            return None
            
        data = [
            ['File:', img_info['name']],
            ['Size:', img_info['size']],
            ['Dimensions:', f"{img_info['width']}x{img_info['height']} px"],
            ['MD5:', img_info.get('md5', 'N/A')]
        ]
        
        # Create table with metadata
        table = Table(data, colWidths=[60, 200])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'NotoSans'),  # Use NotoSans instead of DejaVuSans
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.gray),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT' if align_right else 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0, colors.white),  # No visible grid
        ]))
        return table

    def process_image_message(self, message, img_path, elements, styles):
        """Process and add an image message to the PDF"""
        try:
            # Get image info
            img_info = self.get_image_info(img_path)
            if not img_info:
                return

            # Determine if this is the device owner's message
            is_owner = message.sender == self.device_owner
            
            # Calculate image dimensions
            max_width = 300  # Maximum width for images
            width = min(img_info['width'], max_width)
            height = (width / img_info['width']) * img_info['height']
            
            # Create image element
            img = Image(img_path, width=width, height=height)
            
            # Create metadata table
            meta_table = self.format_image_metadata(img_info, align_right=is_owner)  # Reversed alignment
            
            # Create a table to hold both image and metadata
            if is_owner:
                # Owner's messages: image left, metadata right
                data = [[img, meta_table if meta_table else '']]
                align = 'LEFT'
            else:
                # Others' messages: metadata left, image right
                data = [[meta_table if meta_table else '', img]]
                align = 'RIGHT'
            
            # Create and style the container table
            container = Table(data, colWidths=[max_width, 260])
            container.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), align),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 20),
                ('RIGHTPADDING', (0, 0), (-1, -1), 20),
                ('GRID', (0, 0), (-1, -1), 0, colors.white),  # No visible grid
            ]))
            
            # Add sender name with correct alignment
            elements.append(Paragraph(message.sender, 
                styles['ChatLeft' if is_owner else 'ChatRight']))  # Reversed to match message alignment
            
            # Add the container with image and metadata
            elements.append(container)
            elements.append(Spacer(1, 10))  # Add some space after the image
            
        except Exception as e:
            debug_print(f"Error processing image: {str(e)}")
            elements.append(Paragraph(f"[Error loading image: {os.path.basename(img_path)}]",
                styles['Normal']))

    def is_emoji_supported(self, char):
        """Check if an emoji is supported by ReportLab's default fonts"""
        try:
            # Only the most basic and commonly supported emoji ranges
            supported_ranges = [
                (0x2600, 0x26FF),    # Basic symbols (⚡, ☀, etc.)
                (0x2700, 0x27BF),    # Basic dingbats (✅, ✨, etc.)
                (0x1F600, 0x1F64F),  # Basic emoticons (😊, 😂, etc.)
            ]
            code = ord(char)
            return any(start <= code <= end for start, end in supported_ranges)
        except:
            return False

    def process_emojis(self, text):
        """Convert only unsupported emojis to text while keeping supported ones"""
        if not text:
            return text
            
        result = []
        for char in text:
            if emoji.is_emoji(char):
                if not self.is_emoji_supported(char):
                    # Convert only unsupported emoji to text
                    emoji_name = emoji.demojize(char)
                    emoji_name = emoji_name.replace(':', '').replace('_', ' ')
                    result.append(f"({emoji_name})")
                else:
                    result.append(char)  # Keep supported emoji as is
            else:
                result.append(char)
        return ''.join(result)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse WhatsApp chat export ZIP file and generate PDF')
    parser.add_argument('zip_file', help='Path to WhatsApp chat export ZIP file')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--debug-attachments', action='store_true', help='Enable debug output for attachments')
    parser.add_argument('--device-owner', help='Name of the device owner for message alignment')
    args = parser.parse_args()

    try:
        WhatsAppExportParser.DEBUG = args.debug
        WhatsAppExportParser.DEBUG_ATTACHMENTS = args.debug_attachments
        wa_parser = WhatsAppExportParser(args.zip_file, args.device_owner)
        wa_parser.unpack_zip()
        wa_parser.parse_chats()
        wa_parser.scan_chat_members()
        wa_parser.check_media_files()
        wa_parser.print_attachment_stats()  # Get stats before generating PDF
        wa_parser.generate_pdf(str(Path(args.zip_file).with_suffix('.pdf')))
    except Exception as e:
        print(f"\nError processing WhatsApp export: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()
