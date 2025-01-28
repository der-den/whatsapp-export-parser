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
    def __init__(self, output_dir: str, unzip_dir: Optional[str] = None, input_filename: Optional[str] = None, config: Optional[Dict] = None):
        """Initialize the PDF attachment generator.
        
        Args:
            output_dir (str): Directory where individual PDF files will be saved
            unzip_dir (Optional[str]): Directory where attachments are extracted
            input_filename (Optional[str]): Name of the input chat file
            config (Optional[Dict]): Configuration dictionary including language settings
        """
        self.output_dir = output_dir
        self.unzip_dir = unzip_dir
        self.input_filename = input_filename
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
                        "Sender": msg.sender,
                        "Timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
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
            
            # Handle PDFs (just copy them)
            if attachment_path.lower().endswith('.pdf'):
                shutil.copy2(attachment_path, output_pdf)
                return output_pdf
            
            # Handle images
            if any(attachment_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                return self._create_image_pdf(attachment_path, output_pdf, metadata)
            
            # Handle audio files
            if any(attachment_path.lower().endswith(ext) for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.opus']):
                return self._create_audio_pdf(attachment_path, output_pdf, metadata)
                
            return None
            
        except Exception as e:
            print(f"Error generating PDF for {attachment_path}: {str(e)}")
            return None

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
        
        # Limit to 9 frames (3x3 grid)
        frames_data = frames_data[:9]
        grid_size = 3  # Fixed 3x3 grid
        
        # Create grid data
        grid_data = []
        row = []
        for i, frame_path in enumerate(frames_data):
            # Add frame to grid
            row.append(Image(frame_path, width=100, height=100))
            
            # Start new row if needed
            if (i + 1) % grid_size == 0:
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

    def _create_image_pdf(self, image_path: str, output_pdf: str, metadata: Optional[Dict] = None) -> Optional[str]:
        try:
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
            title = f"{self.lang.get('pdf', 'attachments', 'image')} {self.attachment_counter}"
            elements.append(Paragraph(title, self.styles['AttachmentTitle']))
            elements.append(Spacer(1, 10))
            
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
            
            # Add metadata BEFORE content
            if metadata:
                for key, value in metadata.items():
                    # Skip frames data and size for WebPs with frames
                    if key != 'frames' and value and not (has_frames and key == 'size_bytes'):
                        elements.append(Paragraph(f"{key}: {value}", self.styles['AttachmentMetadata']))
                elements.append(Spacer(1, 20))
            
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
            
            # Build PDF with header/footer
            doc.build(elements, onFirstPage=self._create_header_footer, onLaterPages=self._create_header_footer)
            return output_pdf
            
        except Exception as e:
            print(f"Error creating PDF for image {image_path}: {str(e)}")
            return None

    def _create_audio_pdf(self, audio_path: str, output_pdf: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """Create a PDF for an audio file, showing metadata and an audio icon."""
        try:
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
            title = f"{self.lang.get('pdf', 'attachments', 'audio')} {self.attachment_counter}"
            elements.append(Paragraph(title, self.styles['AttachmentTitle']))
            elements.append(Spacer(1, 10))
            
            # Add metadata
            if metadata:
                meta_list = []
                
                # Basic metadata
                if 'duration_seconds' in metadata:
                    duration = float(metadata['duration_seconds'])
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    meta_list.append(f"{self.lang.get('pdf', 'audio', 'duration')}: {minutes}:{seconds:02d}")
                
                if 'size_bytes' in metadata:
                    size_mb = float(metadata['size_bytes']) / (1024 * 1024)
                    meta_list.append(f"{self.lang.get('pdf', 'audio', 'size')}: {size_mb:.1f} MB")
                
                if 'md5_hash' in metadata:
                    meta_list.append(f"MD5: {metadata['md5_hash']}")
                
                if 'filename' in metadata:
                    meta_list.append(f"{self.lang.get('pdf', 'header', 'filename')}: {metadata['filename']}")
                
                if 'timestamp' in metadata:
                    meta_list.append(f"{self.lang.get('pdf', 'header', 'timestamp')}: {metadata['timestamp']}")
                
                # Add metadata paragraphs
                for meta_item in meta_list:
                    elements.append(Paragraph(meta_item, self.styles['AttachmentMetadata']))
                elements.append(Spacer(1, 20))
                
                # Add transcription if available
                if 'transcription' in metadata:
                    trans = metadata['transcription']
                    
                    # Add transcription metadata
                    elements.append(Paragraph(self.lang.get('pdf', 'audio', 'transcription'), self.styles['AttachmentTitle']))
                    elements.append(Spacer(1, 5))
                    
                    if 'language' in trans:
                        elements.append(Paragraph(f"{self.lang.get('pdf', 'audio', 'language')}: {trans['language']}", self.styles['AttachmentMetadata']))
                    if 'model' in trans:
                        elements.append(Paragraph(f"{self.lang.get('pdf', 'audio', 'model')}: {trans['model']}", self.styles['AttachmentMetadata']))
                    
                    elements.append(Spacer(1, 10))
                    elements.append(Paragraph(self.lang.get('pdf', 'audio', 'transcription_warning'), self.styles['AttachmentMetadata']))
                    elements.append(Spacer(1, 5))
                    
                    if 'text' in trans:
                        elements.append(Paragraph(trans['text'], self.styles['Normal']))
                    else:
                        elements.append(Paragraph(self.lang.get('pdf', 'audio', 'no_transcription'), self.styles['AttachmentMetadata']))
            
            # Build PDF with header/footer
            doc.build(elements, onFirstPage=self._create_header_footer, onLaterPages=self._create_header_footer)
            return output_pdf
            
        except Exception as e:
            print(f"{self.lang.get('errors', 'audio_pdf')}: {str(e)}")
            return None
