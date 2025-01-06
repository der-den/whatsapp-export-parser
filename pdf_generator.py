from typing import List, Optional, Tuple, Dict, Union
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, KeepTogether, HRFlowable, Frame
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
import sys
import os

from models import ChatMessage, ContentType
from utils import format_size, debug_print
from vcf_handler import VCFHandler, ContactInfo
from chat_parser import ChatParser

class PDFGenerator:
    def __init__(self, output_path: str, device_owner: Optional[str] = None, 
                 unzip_dir: Optional[str] = None, header_text: Optional[str] = None,
                 footer_text: Optional[str] = None, input_filename: Optional[str] = None,
                 zip_size: Optional[int] = None, zip_md5: Optional[str] = None,
                 no_attachments: bool = False):
        self.output_path = output_path
        self.device_owner = device_owner
        self.unzip_dir = unzip_dir
        self.header_text = header_text
        self.footer_text = footer_text
        self.input_filename = input_filename
        self.zip_size = zip_size
        self.zip_md5 = zip_md5
        self.no_attachments = no_attachments
        self.font_path = os.path.join(os.path.dirname(__file__), "fonts")
        self.main_font = "DejaVuSans"
        self.emoji_font = "Symbola"
        
        # Register fonts
        pdfmetrics.registerFont(TTFont(self.main_font, os.path.join(self.font_path, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(self.emoji_font, os.path.join(self.font_path, "Symbola.ttf")))
        
        # Create a font mapping that uses both fonts
        pdf_fonts = {
            'normal': self.main_font,
            'emoji': self.emoji_font
        }
        
        # Create a paragraph style that uses the font mapping
        self.style = ParagraphStyle(
            'default',
            fontName=self.main_font,
            fontSize=10,
            leading=12,
            wordWrap='CJK'  # This helps with emoji wrapping
        )
        
        self.styles = getSampleStyleSheet()
        
        # Update existing styles to use our fonts
        for style in self.styles.byName.values():
            style.fontName = self.main_font
        
        # Definiere Farben für den Hintergrund der Nachrichten
        self.owner_color = colors.Color(0.98, 0.99, 0.98)  # Sehr helles Grün
        self.other_color = colors.Color(0.98, 0.98, 0.98)  # Sehr helles Grau
        
        self._setup_styles()
        
    def _setup_styles(self):
        """Setup custom styles for the PDF"""
        # Basic timestamp style for statistics
        self.styles.add(ParagraphStyle(
            name='Timestamp',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.gray,
            spaceAfter=0,
            spaceBefore=0,
            leading=10
        ))
        
        # Timestamp styles
        self.styles.add(ParagraphStyle(
            name='TimestampOwner',
            parent=self.styles['Normal'],
            fontSize=5,
            textColor=colors.gray,
            spaceAfter=0,
            spaceBefore=0,
            leading=6,
            alignment=TA_LEFT
        ))
        
        self.styles.add(ParagraphStyle(
            name='TimestampOther',
            parent=self.styles['Normal'],
            fontSize=5,
            textColor=colors.gray,
            spaceAfter=0,
            spaceBefore=0,
            leading=6,
            alignment=TA_RIGHT
        ))
        
        # Sender styles
        self.styles.add(ParagraphStyle(
            name='SenderOwner',
            parent=self.styles['Normal'],
            fontSize=5,
            textColor=colors.gray,
            spaceAfter=0,
            spaceBefore=0,
            leading=6,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'  # Fett für Namen
        ))
        
        self.styles.add(ParagraphStyle(
            name='SenderOther',
            parent=self.styles['Normal'],
            fontSize=5,
            textColor=colors.gray,
            spaceAfter=0,
            spaceBefore=0,
            leading=6,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'  # Fett für Namen
        ))
        
        # Message styles
        self.styles.add(ParagraphStyle(
            name='MessageOwner',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
            textColor=colors.black,
            wordWrap='CJK',
            spaceAfter=0,
            spaceBefore=0
        ))
        
        self.styles.add(ParagraphStyle(
            name='MessageOther',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=12,
            alignment=TA_RIGHT,
            textColor=colors.black,
            wordWrap='CJK',
            spaceAfter=0,
            spaceBefore=0
        ))

        self.styles.add(ParagraphStyle(
            name='ContactInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=11,
            leftIndent=20,
            wordWrap='CJK',
            spaceAfter=0,
            spaceBefore=0
        ))

    def _create_header_footer(self, canvas, doc):
        """Add header and footer to each page"""
        canvas.saveState()
        
        # Set font and color for header/footer
        canvas.setFont(self.main_font, 8)
        canvas.setFillColor(colors.gray)
        
        # Add header if specified
        if self.header_text:
            canvas.drawString(doc.leftMargin, doc.pagesize[1] - doc.topMargin/2, 
                            str(self.header_text))
        
        # Add footer if specified
        if self.footer_text:
            footer_text = f"{self.footer_text} - Page {canvas.getPageNumber()}"
        else:
            footer_text = f"Page {canvas.getPageNumber()}"
            
        canvas.drawString(doc.leftMargin, doc.bottomMargin/2, footer_text)
        
        canvas.restoreState()

    def _escape_text(self, text: str) -> str:
        """Escape special characters in text for ReportLab paragraphs"""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))

    def _format_text(self, text: str) -> str:
        """Format text with appropriate font tags for emojis"""
        import re
        # Unicode ranges for emojis
        emoji_pattern = re.compile(
            "["
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251" 
            "]+"
        )
        
        # Replace emojis with font-tagged versions
        def replace_emoji(match):
            return f'<font name="{self.emoji_font}" size="12">{match.group()}</font>'
            
        # First escape the text, then replace emojis
        safe_text = self._escape_text(text)
        return emoji_pattern.sub(replace_emoji, safe_text)

    def _format_message(self, message: ChatMessage) -> List:
        """Format a single message for PDF generation"""
        elements = []
        
        # Determine if message is from device owner
        is_owner = (self.device_owner and message.sender == self.device_owner)
        
        # Split long messages into smaller chunks if needed
        content = ''.join(c for c in message.content if c.isprintable()).strip()
        if len(content) > 1000:  # If message is very long
            content = content[:997] + "..."  # Truncate with ellipsis
        
        # Format timestamp, sender and content
        timestamp_text = message.timestamp.strftime("%Y-%m-%d %H:%M")
        safe_sender = self._escape_text(message.sender)
        safe_content = self._format_text(content)
        
        # Create paragraphs for each component
        timestamp_style = self.styles['TimestampOwner'] if is_owner else self.styles['TimestampOther']
        timestamp_para = Paragraph(timestamp_text, timestamp_style)
        sender_style = self.styles['SenderOwner'] if is_owner else self.styles['SenderOther']
        sender_para = Paragraph(safe_sender, sender_style)
        message_style = self.styles['MessageOwner'] if is_owner else self.styles['MessageOther']
        content_para = Paragraph(safe_content, message_style)
        
        # Create inner table for timestamp and sender
        meta_table = Table(
            [[timestamp_para],
             [sender_para]],
            colWidths=[60],  # Fixed width for meta information
            style=TableStyle([
                ('LEFTPADDING', (0,0), (-1,-1), 2),
                ('RIGHTPADDING', (0,0), (-1,-1), 2),
                ('TOPPADDING', (0,0), (-1,-1), 1),
                ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                ('ALIGN', (0,0), (-1,-1), 'RIGHT' if not is_owner else 'LEFT'),  
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ])
        )
        
        # Create outer table with meta info and content
        if is_owner:
            table_data = [[meta_table, content_para]]
        else:
            table_data = [[content_para, meta_table]]  # Umgekehrte Reihenfolge für Other
            
        available_width = A4[0] - 2*36  # Page width minus margins
        col_widths = ([60, available_width - 60] if is_owner 
                     else [available_width - 60, 60])  # Angepasste Breiten
        
        # Create message table with correct alignment
        message_table = Table(
            table_data,
            colWidths=col_widths,
            style=TableStyle([
                ('LEFTPADDING', (0,0), (-1,-1), 2),
                ('RIGHTPADDING', (0,0), (-1,-1), 2),
                ('TOPPADDING', (0,0), (-1,-1), 2),
                ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                ('BACKGROUND', (0,0), (-1,-1), self.owner_color if is_owner else self.other_color),
                ('ALIGN', (0,0), (-1,-1), 'RIGHT' if not is_owner else 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ])
        )
        
        elements.append(message_table)
        
        # Handle attachments
        if message.is_attachment and message.exists_in_export:
            debug_print(f"Loading attachment: {message.attachment_file}")
            if not self.no_attachments:
                try:
                    # Remove invisible characters from filename before processing
                    clean_filename = ''.join(c for c in message.attachment_file if c.isprintable()).strip()
                    full_path = self._get_full_path(clean_filename)
                    
                    if full_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        # Handle images
                        try:
                            max_width = 400  # Maximum width for images
                            max_height = 400  # Maximum height for images
                            scaled_width, scaled_height = self._scale_image(full_path, max_width, max_height)
                            
                            img = Image(full_path, width=scaled_width, height=scaled_height)
                            elements.append(img)
                        except Exception as e:
                            print(f"Error processing image: {str(e)}", file=sys.stderr)
                            error_text = f"[Error loading image: {str(e)}]"
                            elements.append(Paragraph(error_text, self.styles['Normal']))
                except Exception as e:
                    print(f"Error adding attachment to PDF: {str(e)}", file=sys.stderr)
                    error_text = f"[Error loading attachment: {str(e)}]"
                    elements.append(Paragraph(error_text, self.styles['Normal']))
        
        return elements

    def _get_full_path(self, filename: str) -> str:
        """Get full path for an attachment file"""
        if self.unzip_dir:
            return str(Path(self.unzip_dir) / filename)
        return filename

    def _format_contact_info(self, contact: ContactInfo) -> List:
        """Format contact information for the PDF"""
        contact_elements = []
        
        # Add name
        contact_elements.append(Paragraph(
            f"<b>Contact:</b> {contact.full_name}",
            self.styles['ContactInfo']
        ))
        
        # Add phone numbers
        if contact.phone_numbers:
            contact_elements.append(Paragraph(
                f"<b>Phone:</b> {', '.join(contact.phone_numbers)}",
                self.styles['ContactInfo']
            ))
            
        # Add emails
        if contact.emails:
            contact_elements.append(Paragraph(
                f"<b>Email:</b> {', '.join(contact.emails)}",
                self.styles['ContactInfo']
            ))
            
        # Add organization
        if contact.organization:
            contact_elements.append(Paragraph(
                f"<b>Organization:</b> {contact.organization}",
                self.styles['ContactInfo']
            ))
            
        # Add title
        if contact.title:
            contact_elements.append(Paragraph(
                f"<b>Title:</b> {contact.title}",
                self.styles['ContactInfo']
            ))
            
        # Add addresses
        if contact.addresses:
            contact_elements.append(Paragraph(
                f"<b>Address:</b> {', '.join(contact.addresses)}",
                self.styles['ContactInfo']
            ))
            
        return contact_elements

    def _format_statistics(self, statistics, chat_members, messages):
        """Format statistics for the PDF"""
        elements = []
        
        if not statistics:
            return elements
            
        # Create a smaller heading style for "Messages by Sender"
        small_heading_style = ParagraphStyle(
            'SmallHeading2',
            parent=self.styles['Normal'],  
            fontSize=10,  
            fontName='Helvetica-Bold',  
            textColor=colors.black,  
            spaceAfter=6,
            leftIndent=6
        )
        
        # Create statistics table
        stat_data = [
            ["Report created on:", datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ]
        
        # Add ZIP file information if available
        if self.input_filename:
            stat_data.extend([
                ["ZIP Filename:", os.path.basename(self.input_filename)],
                ["ZIP Size:", format_size(self.zip_size) if self.zip_size else "Unknown"],
                ["ZIP MD5 Hash:", self.zip_md5 or "Unknown"],
            ])
        
        # Add chat statistics
        stat_data.extend([
            ["Total Messages:", str(statistics.total_messages)],
            ["Chat Members:", str(len(chat_members))],
            ["Media Files:", str(sum(1 for m in messages if m.is_attachment))],
            ["Time Span:", f"{messages[0].timestamp.date()} to {messages[-1].timestamp.date()}"]
        ])
        
        if statistics.edited_messages:
            stat_data.append(["Edited Messages:", str(statistics.edited_messages)])
            
        if statistics.total_media_duration:
            hours = int(statistics.total_media_duration // 3600)
            minutes = int((statistics.total_media_duration % 3600) // 60)
            seconds = int(statistics.total_media_duration % 60)
            duration_str = f"{hours}h {minutes}m {seconds}s"
            stat_data.append(["Total Media Duration:", duration_str])
            
        if statistics.attachment_sizes:
            total_size = sum(statistics.attachment_sizes.values())
            stat_data.append(["Total Media Size:", format_size(total_size)])
            
        # Calculate available width
        available_width = A4[0] - 2*36  # Page width minus margins
        col_widths = [available_width * 0.3, available_width * 0.7]
            
        stat_table = Table(stat_data, colWidths=col_widths)
        stat_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.gray),
        ]))
        
        elements.append(stat_table)
        elements.append(Spacer(1, 10))  
        
        # Add Messages by Sender section with smaller heading
        if hasattr(statistics, 'messages_by_sender') and statistics.messages_by_sender:
            elements.append(Paragraph("Participants and message counter:", small_heading_style))
            
            # Create style for sender entries that matches table alignment
            sender_style = ParagraphStyle(
                'SenderStats',
                parent=self.styles['Normal'],
                fontSize=10,
                leftIndent=col_widths[0] + 6
            )
            
            for sender, count in statistics.messages_by_sender.most_common():
                display_name = f"{sender} (Owner)" if sender == self.device_owner else sender
                elements.append(Paragraph(f"{display_name}: {count}", sender_style))
            
            elements.append(Spacer(1, 15))
        
        return elements

    def _scale_image(self, image_path: str, max_width: float, max_height: float) -> tuple:
        """Scale image dimensions while maintaining aspect ratio"""
        try:
            with PILImage.open(image_path) as img:
                img_width, img_height = img.size
                width_ratio = max_width / img_width
                height_ratio = max_height / img_height
                scale_ratio = min(width_ratio, height_ratio)
                
                new_width = img_width * scale_ratio
                new_height = img_height * scale_ratio
                
                return new_width, new_height
        except Exception as e:
            print(f"Error scaling image {image_path}: {str(e)}", file=sys.stderr)
            return max_width, max_height  

    def generate_pdf(self, messages: List[ChatMessage], chat_members: set, statistics: Optional[ChatParser.ChatStatistics] = None) -> None:
        """
        Generiert ein PDF-Dokument aus den Chat-Nachrichten.
        
        Args:
            messages: Liste der Chat-Nachrichten
            chat_members: Set of chat members
            statistics: Optional chat statistics
        """
        print(f"\nStarting PDF generation with {len(messages)} messages...")
        
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=A4,
            rightMargin=26,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        elements = []
        
        # Add chat name as header
        if self.input_filename:
            header_style = ParagraphStyle(
                'Header',
                parent=self.styles['Heading1'],
                fontName=self.main_font,
                fontSize=16,
                spaceAfter=20,
                alignment=TA_CENTER
            )
            # Remove .zip extension if present
            chat_name = Path(self.input_filename).stem
            if chat_name.endswith('.zip'):
                chat_name = chat_name[:-4]
            elements.append(Paragraph(chat_name, header_style))
            elements.append(Spacer(1, 10))
        
        # Add custom header text if provided
        if self.header_text:
            custom_header_style = ParagraphStyle(
                'CustomHeader',
                parent=self.styles['Heading2'],
                fontName=self.main_font,
                fontSize=14,
                spaceAfter=20
            )
            elements.append(Paragraph(self.header_text, custom_header_style))
        
        # Add statistics if provided
        print("Adding statistics...")
        elements.extend(self._format_statistics(statistics, chat_members, messages))
        
        # Process messages
        print("Adding messages...")
        for message in messages:
            elements.extend(self._format_message(message))
            
        # Add footer if provided
        if self.footer_text:
            footer_style = ParagraphStyle(
                'Footer',
                parent=self.styles['Normal'],
                fontName=self.main_font,
                fontSize=10,
                textColor=colors.gray
            )
            elements.append(PageBreak())
            elements.append(Paragraph(self.footer_text, footer_style))
        
        # Build the PDF
        print("Building PDF...")
        doc.build(elements, onFirstPage=self._create_header_footer, onLaterPages=self._create_header_footer)
