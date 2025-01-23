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

from models import ChatMessage

class PDFAttachmentGenerator:
    def __init__(self, output_dir: str, unzip_dir: Optional[str] = None, input_filename: Optional[str] = None):
        """Initialize the PDF attachment generator.
        
        Args:
            output_dir (str): Directory where individual PDF files will be saved
            unzip_dir (Optional[str]): Directory where attachments are extracted
            input_filename (Optional[str]): Name of the input chat file
        """
        self.output_dir = output_dir
        self.unzip_dir = unzip_dir
        self.input_filename = input_filename
        self.attachment_counter = 0
        self.font_path = os.path.join(os.path.dirname(__file__), "fonts")
        self.main_font = "DejaVuSans"
        self.emoji_font = "Symbola"
        
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
            spaceAfter=20,
            alignment=TA_CENTER
        ))
        
        # Attachment title style
        self.styles.add(ParagraphStyle(
            name='AttachmentTitle',
            parent=self.styles['Heading1'],
            fontSize=14,
            spaceAfter=15,
            spaceBefore=15,
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
                            print(f"Generated PDF for attachment: {os.path.basename(pdf_path)}", end="\r")
                            pdfs_generated += 1
                except Exception as e:
                    print(f"Error processing message attachment: {str(e)}")
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
        
        # Add chat name as header if available
        if self.input_filename:
            chat_name = Path(self.input_filename).stem
            if chat_name.endswith('.zip'):
                chat_name = chat_name[:-4]
            canvas.drawString(doc.leftMargin, doc.pagesize[1] - doc.topMargin/2, chat_name)
        
        # Add page number as footer
        footer_text = f"Page {canvas.getPageNumber()}"
        canvas.drawString(doc.leftMargin, doc.bottomMargin/2, footer_text)
        
        canvas.restoreState()

    def _create_image_pdf(self, image_path: str, output_pdf: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """Create a PDF containing the image and metadata.
        
        Args:
            image_path (str): Path to the image file
            output_pdf (str): Path where to save the PDF
            metadata (dict, optional): Metadata to include in the PDF
            
        Returns:
            str: Path to the generated PDF file, or None if generation failed
        """
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
                # Remove .zip extension if present
                chat_name = Path(self.input_filename).stem
                if chat_name.endswith('.zip'):
                    chat_name = chat_name[:-4]
                elements.append(Paragraph(chat_name, self.styles['Header']))
                elements.append(Spacer(1, 10))
            
            # Add attachment title
            title = f"Attachment {self.attachment_counter}"
            elements.append(Paragraph(title, self.styles['AttachmentTitle']))
            
            # Add metadata BEFORE the image
            if metadata:
                elements.append(Paragraph("Information:", self.styles['Heading2']))
                elements.append(Spacer(1, 10))
                for key, value in metadata.items():
                    if value:
                        elements.append(Paragraph(f"{key}: {value}", self.styles['AttachmentMetadata']))
                elements.append(Spacer(1, 20))
            
            # Process image
            img = PILImage.open(image_path)
            
            # Convert RGBA to RGB if necessary
            if img.mode == 'RGBA':
                bg = PILImage.new('RGB', img.size, 'white')
                bg.paste(img, mask=img.split()[3])
                img = bg
            
            # Calculate dimensions to fit on page with 50% reduction
            # First calculate max available space
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
            elements.append(Spacer(1, 20))
            
            # Build PDF with header/footer
            doc.build(elements, onFirstPage=self._create_header_footer, onLaterPages=self._create_header_footer)
            return output_pdf
            
        except Exception as e:
            print(f"Error creating PDF for image {image_path}: {str(e)}")
            return None
