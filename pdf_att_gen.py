#!/usr/bin/env python3

from typing import List, Optional, Dict
from pathlib import Path
from datetime import datetime
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
import os
import shutil
import sys
import json
import math
from models import ChatMessage
from webp_handler import check_webp_animation, extract_sticker_frames
from languages import load_language, DEFAULT_LANGUAGE

class PDFAttachmentGenerator:
    def __init__(self, output_dir: str, unzip_dir: Optional[str] = None, input_filename: Optional[str] = None, config: Optional[Dict] = None, zip_handler=None):
        """Initialize the PDF attachment generator.
        
        Args:
            output_dir (str): Directory where individual PDF files will be saved
            unzip_dir (Optional[str]): Directory where attachments are extracted
            input_filename (Optional[str]): Name of the input chat file
            config (Optional[Dict]): Configuration dictionary including language settings
            zip_handler: Optional ZipHandler instance for accessing extracted files
        """
        self.output_dir = output_dir
        self.unzip_dir = unzip_dir
        self.input_filename = input_filename
        self.zip_handler = zip_handler
        self.attachment_counter = 0
        self.font_path = os.path.join(os.path.dirname(__file__), "fonts")
        self.main_font = "DejaVuSans"
        self.emoji_font = "Symbola"
        
        # Load language strings
        app_lang = config.get('app_lang', DEFAULT_LANGUAGE) if config else DEFAULT_LANGUAGE
        self.lang = load_language(app_lang)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Register fonts
        pdfmetrics.registerFont(TTFont(self.main_font, os.path.join(self.font_path, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(self.emoji_font, os.path.join(self.font_path, "Symbola.ttf")))
        
        self.styles = getSampleStyleSheet()
        
        # Update existing styles to use our fonts
        for style in self.styles.byName.values():
            style.fontName = self.main_font
            
        self._setup_styles()

    def _get_full_path(self, filename: str) -> str:
        """Get full path for an attachment file."""
        if self.unzip_dir:
            return os.path.join(self.unzip_dir, filename)
        return filename
        
    def _setup_styles(self):
        """Setup custom styles for the PDF"""
        # Header style for chat name
        self.styles.add(ParagraphStyle(
            name='Header',
            parent=self.styles['Heading1'],
            fontName=self.main_font,
            fontSize=16,
            spaceAfter=5,
            spaceBefore=0,
            alignment=TA_LEFT
        ))
        
        # Attachment title style
        self.styles.add(ParagraphStyle(
            name='AttachmentTitle',
            parent=self.styles['Heading1'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=0,
            alignment=TA_LEFT
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='AttachmentMetadata',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=5,
            spaceBefore=5,
            leftIndent=20
        ))

    def process_messages(self, messages: List[ChatMessage]) -> int:
        """Process all messages and generate PDFs for attachments.
        
        Args:
            messages (list): List of chat messages to process
            
        Returns:
            int: Number of PDFs generated
        """
        pdfs_generated = 0
        for msg in messages:
            if msg.is_attachment and msg.exists_in_export and msg.attachment_file:
                try:
                    metadata = json.loads(msg.content) if msg.content else {}
                    metadata.update({
                        "sender": msg.sender,
                        "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    full_path = self._get_full_path(msg.attachment_file)
                    if os.path.exists(full_path):
                        pdf_path = self.generate_pdf_for_attachment(full_path, metadata)
                        if pdf_path:
                            print(self.lang.get('info', 'attachment_pdf_progress').format(os.path.basename(pdf_path)), end="\r")
                            pdfs_generated += 1
                except Exception as e:
                    print(f"{self.lang.get('errors', 'general').format(str(e))}")
                    continue
                    
        return pdfs_generated

    def generate_pdf_for_attachment(self, attachment_path: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """Generate a single PDF file for the given attachment.
        
        Args:
            attachment_path (str): Path to the attachment file
            metadata (dict, optional): Additional metadata about the attachment
        
        Returns:
            str: Path to the generated PDF file, or None if generation failed
        """
        try:
            self.attachment_counter += 1
            output_pdf = os.path.join(self.output_dir, f"Attachment {self.attachment_counter}.pdf")
            
            # Create PDF document with header/footer
            doc = SimpleDocTemplate(
                output_pdf,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            elements = []
            
            # Add chat name header if input filename is available
            if self.input_filename:
                chat_name = Path(self.input_filename).stem
                if chat_name.endswith('.zip'):
                    chat_name = chat_name[:-4]
                elements.append(Paragraph(chat_name, self.styles['Header']))
                elements.append(Spacer(1, 5))
            
            # Add attachment title
            title = f"Attachment #{self.attachment_counter}"
            elements.append(Paragraph(title, self.styles['AttachmentTitle']))
            elements.append(Spacer(1, 10))
            
            # Add common metadata
            self._add_common_metadata(elements, attachment_path, metadata)
            
            # Setup file type handlers
            file_type_handlers = {
                'image': {
                    'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                    'handler': self._create_image_pdf
                },
                'audio': {
                    'extensions': ['.mp3', '.wav', '.ogg', '.m4a', '.opus'],
                    'handler': self._create_audio_pdf
                },
                'video': {
                    'extensions': ['.mp4', '.mov', '.avi', '.webm'],
                    'handler': self._create_video_pdf
                }
            }
            
            # Find handler for file type
            file_extension = Path(attachment_path).suffix.lower()
            content_elements = None
            known_extension = False
            
            # Check each type handler
            for type_info in file_type_handlers.values():
                if file_extension in type_info['extensions']:
                    known_extension = True
                    content_elements = type_info['handler'](attachment_path, metadata)
                    break
            
            # Handle unknown file type
            if not known_extension:
                elements.append(Paragraph(f"Unknown / Not supported file type: {file_extension}", self.styles['AttachmentMetadata']))
            
            if content_elements:
                elements.extend(content_elements)
                doc.build(elements, onFirstPage=self._create_header_footer, onLaterPages=self._create_header_footer)
                return output_pdf
                
            return None
            
        except Exception as e:
            print(f"Error generating PDF for {attachment_path}: {str(e)}")
            return None

    def _add_common_metadata(self, elements: List, attachment_path: str, metadata: Optional[Dict] = None) -> None:
        """Add common metadata elements that should appear in all attachment PDFs.
        
        Args:
            elements: List of PDF elements to append to
            attachment_path: Path to the attachment file
            metadata: Optional metadata dictionary
        """
        if not metadata:
            return
            
        size_bytes = metadata.get('size_bytes', 0)
        if size_bytes < 1024:
            size_bytes_formated = f"{size_bytes} B"
        elif size_bytes < 1024*1024:
            size_bytes_formated = f"{size_bytes/1024:.1f} KB"
        else:
            size_bytes_formated = f"{size_bytes/1024/1024:.1f} MB"

        if 'filename' in metadata:
            elements.append(Paragraph(f"{self.lang.get('pdf', 'header', 'filename')}: {metadata['filename']}", self.styles['AttachmentMetadata']))
        elements.append(Paragraph(f"{self.lang.get('attachments', 'file_size')}: {size_bytes_formated}", self.styles['AttachmentMetadata']))
        
        if 'md5_hash' in metadata:
            elements.append(Paragraph(f"MD5: {metadata['md5_hash']}", self.styles['AttachmentMetadata']))
        
        elements.append(Spacer(1, 10))
        
        # Sender und Timestamp können sowohl groß als auch klein geschrieben sein
        sender = metadata.get('Sender') or metadata.get('sender')
        timestamp = metadata.get('Timestamp') or metadata.get('timestamp')
        
        if sender:
            elements.append(Paragraph(f"{self.lang.get('pdf', 'header', 'sender')}: {sender}", self.styles['AttachmentMetadata']))
        
        if timestamp:
            elements.append(Paragraph(f"{self.lang.get('pdf', 'header', 'timestamp')}: {timestamp}", self.styles['AttachmentMetadata']))
        
        elements.append(Spacer(1, 10))

    def _create_header_footer(self, canvas, doc):
        """Add header and footer to each page"""
        canvas.saveState()
        
        # Set font and color for header/footer
        canvas.setFont(self.main_font, 8)
        canvas.setFillColor(colors.gray)
        
        
        # Add page number as footer
        footer_text = f"Page {canvas.getPageNumber()}"
        canvas.drawString(doc.leftMargin, doc.bottomMargin/2, footer_text)
        
        canvas.restoreState()

    def _create_frame_grid(self, frames_data: List[str], total_frames: int) -> List:
        """Create a grid of frames from a WebP animation.
        
        Args:
            frames_data: List of paths to frame images
            total_frames: Total number of frames in the animation
            
        Returns:
            List of reportlab elements for the frame grid
        """
        elements = []
        
        if not frames_data:
            return elements
        
        # Add frame count information
        elements.append(Paragraph(f"Animation frames: {total_frames}", self.styles['AttachmentMetadata']))
        elements.append(Spacer(1, 10))
        
        # Select 9 evenly distributed frames
        if total_frames <= 9:
            selected_frames = frames_data[:9]  # Wenn weniger als 9 Frames, nimm alle
        else:
            # Berechne den Abstand zwischen den ausgewählten Frames
            step = (total_frames - 1) / 8  # -1 weil wir bei 0 anfangen und den letzten Frame auch wollen
            
            # Wähle 9 Frames mit gleichmäßigem Abstand
            indices = [int(i * step) for i in range(9)]
            selected_frames = [frames_data[i] for i in indices]
        
        grid_size = 3  # Fixed 3x3 grid
        
        # Create grid data
        grid_data = []
        row = []
        for i, frame_path in enumerate(selected_frames):
            # Add frame to grid
            row.append(Image(frame_path, width=100, height=100))
            
            # Start new row if needed
            if (i + 1) % grid_size == 0:  # Every 3rd image
                grid_data.append(row)
                row = []
        
        # Add any remaining frames in the last row
        if row:
            # Pad with empty cells
            while len(row) < grid_size:
                row.append('')
            grid_data.append(row)
        
        # Create table for the grid
        if grid_data:
            table = Table(
                grid_data,
                colWidths=[120] * grid_size,
                style=TableStyle([
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('LEFTPADDING', (0,0), (-1,-1), 10),
                    ('RIGHTPADDING', (0,0), (-1,-1), 10),
                    ('TOPPADDING', (0,0), (-1,-1), 10),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                ])
            )
            elements.append(table)
            elements.append(Spacer(1, 10))
        
        return elements

    def _create_image_pdf(self, image_path: str, metadata: Optional[Dict] = None) -> Optional[List]:
        """Create elements for an image file, showing metadata and the image itself.
        
        Args:
            image_path: Path to the image file
            metadata: Optional metadata about the image
            
        Returns:
            List of elements to add to the PDF, or None if creation failed
        """
        try:
            elements = []
            
            # Process image to check for frames
            img = PILImage.open(image_path)
            has_frames = False
            
            if image_path.lower().endswith('.webp'):
                try:
                    # Check if animated
                    is_animated, _ = check_webp_animation(image_path)
                    if is_animated:
                        # Create frames directory
                        extract_dir_name = os.path.basename(self.unzip_dir)
                        meta_dir = os.path.join(os.path.dirname(self.unzip_dir), f"{extract_dir_name}_meta")
                        frames_dir = os.path.join(meta_dir, 'frames', f"attachment_{self.attachment_counter}")
                        
                        # Extract frames to check if we'll have a grid
                        frame_paths = extract_sticker_frames(image_path, frames_dir)
                        if frame_paths:
                            has_frames = True
                except Exception as e:
                    print(f"Error checking WebP frames: {str(e)}")
            
            # Add image-specific metadata
            if metadata:
                image_meta = []
                if 'width' in metadata and 'height' in metadata:
                    image_meta.append(f"{self.lang.get('attachments', 'dimensions')}: {metadata['width']}x{metadata['height']} px")
                if 'format' in metadata:
                    image_meta.append(f"{self.lang.get('attachments', 'format')}: {metadata['format']}")
                if 'mode' in metadata:
                    image_meta.append(f"{self.lang.get('attachments', 'color_mode')}: {metadata['mode']}")
                
                if image_meta:
                    for meta in image_meta:
                        elements.append(Paragraph(meta, self.styles['AttachmentMetadata']))
                    elements.append(Spacer(1, 10))
            
            # Add content (either frames or main image)
            if has_frames:
                elements.extend(self._create_frame_grid(frame_paths, len(frame_paths)))
            else:
                # Convert RGBA to RGB if necessary
                if img.mode == 'RGBA':
                    bg = PILImage.new('RGB', img.size, 'white')
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                
                # Calculate dimensions to fit on page with 50% reduction
                max_width = A4[0] - 2*72  # Page width minus margins
                max_height = A4[1] - 4*72  # Page height minus margins and space for text
                
                # Then reduce by 50%
                max_width *= 0.5
                max_height *= 0.5
                
                # Get original image size and calculate aspect ratio
                img_w, img_h = img.size
                aspect = img_h / float(img_w)
                
                # Scale image while maintaining aspect ratio
                if img_w > max_width:
                    img_w = max_width
                    img_h = img_w * aspect
                
                if img_h > max_height:
                    img_h = max_height
                    img_w = img_h / aspect
                
                # Add image centered
                elements.append(Image(image_path, width=img_w, height=img_h))
            
            return elements
            
        except Exception as e:
            print(f"Error while adding data to PDF for image {image_path}: {str(e)}")
            return None

    def _create_audio_pdf(self, audio_path: str, metadata: Optional[Dict] = None) -> Optional[List]:
        """Create elements for an audio file, showing metadata and an audio icon.
        
        Args:
            audio_path: Path to the audio file
            metadata: Optional metadata about the audio file
            
        Returns:
            List of elements to add to the PDF, or None if creation failed
        """
        try:
            elements = []
            
            
            # Add audio-specific metadata
            if metadata:
                if 'duration_seconds' in metadata:
                    duration = metadata['duration_seconds']
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    elements.append(Paragraph(f"{self.lang.get('pdf', 'audio', 'duration')}: {minutes}:{seconds:02d}", self.styles['AttachmentMetadata']))
                
                # Add transcription if available
                if 'transcription' in metadata:
                    trans = metadata['transcription']
                    elements.append(Paragraph(f"{self.lang.get('pdf', 'audio', 'transcription')}:", self.styles['AttachmentMetadata']))
                    
                    if 'text' in trans:
                        elements.append(Paragraph(trans['text'], self.styles['Normal']))
                    else:
                        elements.append(Paragraph(self.lang.get('pdf', 'audio', 'no_transcription'), self.styles['AttachmentMetadata']))
            
            return elements
            
        except Exception as e:
            print(f"{self.lang.get('errors', 'audio_pdf')}: {str(e)}")
            return None

    def _create_video_pdf(self, video_path: str, metadata: Optional[Dict] = None) -> Optional[List]:
        """Create elements for a video file, showing metadata and preview frames.
        
        Args:
            video_path: Path to the video file
            metadata: Optional metadata about the video
            
        Returns:
            List of elements to add to the PDF, or None if creation failed
        """
        try:
            elements = []
            
            # Add video metadata
            if metadata:
                if 'width' in metadata and 'height' in metadata:
                    elements.append(Paragraph(f"{self.lang.get('attachments', 'dimensions')}: {metadata['width']}x{metadata['height']} px", self.styles['AttachmentMetadata']))
                if 'duration_seconds' in metadata:
                    duration = metadata['duration_seconds']
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    elements.append(Paragraph(f"{self.lang.get('attachments', 'duration')}: {minutes}:{seconds:02d}", self.styles['AttachmentMetadata']))
                if 'fps' in metadata:
                    elements.append(Paragraph(f"{self.lang.get('attachments', 'fps')}: {metadata['fps']:.1f}", self.styles['AttachmentMetadata']))
                if 'frame_count' in metadata:
                    elements.append(Paragraph(f"{self.lang.get('attachments', 'frame_count')}: {metadata['frame_count']}", self.styles['AttachmentMetadata']))
                
                elements.append(Spacer(1, 10))
            
                # Add preview frames if available
                if 'preview' in metadata:
                    # Der meta_path ist relativ zum meta_dir
                    meta_dir = os.path.join(os.path.dirname(self.zip_handler.extract_path), os.path.basename(self.zip_handler.extract_path) + "_meta")
                    preview_path = os.path.join(meta_dir, metadata['preview']['meta_path'])
                    
                    if os.path.exists(preview_path):
                        elements.append(Paragraph(self.lang.get('pdf', 'frames'), self.styles['AttachmentMetadata']))
                        elements.append(Spacer(1, 5))
                        
                        # Maximale Breite und Höhe für das Bild
                        max_width = A4[0] - 2*72  # Seitenbreite minus Ränder
                        max_height = A4[1] - 4*72  # Seitenhöhe minus Ränder und Platz für Text
                        
                        # Öffne das Bild und hole die Originaldimensionen
                        img = PILImage.open(preview_path)
                        img_w, img_h = img.size
                        img.close()
                        
                        # Berechne das Seitenverhältnis
                        aspect = img_w / float(img_h)
                        
                        # Skaliere das Bild proportional
                        if max_width / aspect <= max_height:
                            # Breite ist der limitierende Faktor
                            scaled_width = max_width
                            scaled_height = max_width / aspect
                        else:
                            # Höhe ist der limitierende Faktor
                            scaled_height = max_height
                            scaled_width = max_height * aspect
                        
                        elements.append(Image(preview_path, width=scaled_width, height=scaled_height))
            
            return elements
            
        except Exception as e:
            print(f"{self.lang.get('errors', 'video_pdf')}: {str(e)}")
            return None

    def process_messages(self, messages: List[ChatMessage]) -> int:
        """Process all messages and generate PDFs for attachments.
        
        Args:
            messages (list): List of chat messages to process
            
        Returns:
            int: Number of PDFs generated
        """
        pdfs_generated = 0
        for msg in messages:
            if msg.is_attachment and msg.exists_in_export and msg.attachment_file:
                try:
                    metadata = json.loads(msg.content) if msg.content else {}
                    metadata.update({
                        "sender": msg.sender,
                        "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    full_path = self._get_full_path(msg.attachment_file)
                    if os.path.exists(full_path):
                        pdf_path = self.generate_pdf_for_attachment(full_path, metadata)
                        if pdf_path:
                            print(self.lang.get('info', 'attachment_pdf_progress').format(os.path.basename(pdf_path)), end="\r")
                            pdfs_generated += 1
                except Exception as e:
                    print(f"{self.lang.get('errors', 'general').format(str(e))}")
                    continue
                    
        return pdfs_generated
