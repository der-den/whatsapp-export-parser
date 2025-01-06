from dataclasses import dataclass, field
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum, auto

class MimeType(Enum):
    """Common MIME types for chat attachments"""
    # Documents
    PDF = "application/pdf"
    DOC = "application/msword"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    VCF = "text/x-vcard"  # VCF contact card
    
    # Images and Stickers
    PNG = "image/png"
    JPEG = "image/jpeg"
    GIF = "image/gif"
    WEBP = "image/webp"
    
    # Audio
    MP3 = "audio/mpeg"
    OGG = "audio/ogg"
    WAV = "audio/wav"
    M4A = "audio/mp4"
    
    # Video
    MP4 = "video/mp4"
    WEBM = "video/webm"
    MOV = "video/quicktime"
    AVI = "video/x-msvideo"
    THREEGP = "video/3gpp"

class ContentType(Enum):
    """Enum for different types of content in a chat message"""
    # Text and Links
    TEXT = "text/plain"
    LINK = "link"
    
    # Documents
    PDF = "application/pdf"
    MS_POWERPOINT = "application/vnd.ms-powerpoint"
    MS_WORD = "application/msword"
    MS_EXCEL = "application/vnd.ms-excel"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    VCF = "text/x-vcard"  # VCF contact card
    
    # Images and Stickers
    PNG = "image/png"
    JPEG = "image/jpeg"
    GIF = "image/gif"
    WEBP = "image/webp"
    STICKER = "sticker/webp"  # For both static and animated stickers
    
    # Audio
    MP3 = "audio/mpeg3"
    X_MP3 = "audio/x-mpeg-3"
    AAC = "audio/aac"
    MP4_AUDIO = "audio/mp4"
    MPEG_AUDIO = "audio/mpeg"
    AMR = "audio/amr"
    OGG_OPUS = "audio/ogg"  # only opus codecs
    
    # Video
    MP4 = "video/mp4"
    VIDEO_3GP = "video/3gp"
    WEBM = "video/webm"
    MOV = "video/quicktime"
    AVI = "video/x-msvideo"
    
    # Content type categories
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    CONTACT = "contact"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_mime_type(cls, mime_type: str) -> 'ContentType':
        """Get ContentType from MIME type string"""
        if not mime_type:
            return cls.UNKNOWN
            
        mime_type = mime_type.lower()
        
        # First try exact match
        try:
            return next(ctype for ctype in cls if ctype.value == mime_type)
        except StopIteration:
            pass
            
        # If no exact match, try category matching
        if mime_type.startswith('image/'):
            return cls.IMAGE
        if mime_type.startswith('video/'):
            return cls.VIDEO
        if mime_type.startswith('audio/'):
            return cls.AUDIO
        if mime_type.startswith(('application/', 'text/')):
            if mime_type == 'text/x-vcard':
                return cls.CONTACT
            return cls.DOCUMENT
            
        return cls.UNKNOWN

    @property
    def is_video(self) -> bool:
        """Check if content type is a video format"""
        return self in [ContentType.VIDEO, ContentType.MP4, ContentType.VIDEO_3GP, 
                       ContentType.WEBM, ContentType.MOV, ContentType.AVI]

    @property
    def is_image(self) -> bool:
        """Check if content type is an image format"""
        return self in [ContentType.IMAGE, ContentType.PNG, ContentType.JPEG, 
                       ContentType.GIF, ContentType.WEBP]

    @property
    def is_audio(self) -> bool:
        """Check if content type is an audio format"""
        return self in [ContentType.AUDIO, ContentType.MP3, ContentType.X_MP3,
                       ContentType.AAC, ContentType.MP4_AUDIO, ContentType.MPEG_AUDIO,
                       ContentType.AMR, ContentType.OGG_OPUS]

    @property
    def is_document(self) -> bool:
        """Check if content type is a document format"""
        return self in [ContentType.DOCUMENT, ContentType.PDF, ContentType.MS_WORD,
                       ContentType.MS_POWERPOINT, ContentType.MS_EXCEL, ContentType.DOCX,
                       ContentType.PPTX, ContentType.XLSX]

@dataclass
class ChatMessage:
    """Represents a single chat message"""
    timestamp: datetime
    sender: str
    content: str
    content_type: ContentType
    content_length: Optional[int]
    is_attachment: bool
    attachment_file: Optional[str] = None
    exists_in_export: bool = False  # Whether the attachment exists in the export
    is_multiframe: bool = False  # True for animated stickers and videos
    is_edited: bool = False  # Flag to indicate if message was edited

""" 
If VP8X characters exists, it could be static or animated (most images would be animated).

The solution is

Read 4 bytes -> 'RIFF'
Skip 4 bytes
Read 4 bytes -> 'WEBP'
Read 4 bytes -> 'VP8X' / 'VP8L' / 'VP8'
skip 14 bytes
Read 4 bytes -> 'ANIM' """