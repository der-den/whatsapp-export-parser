import vobject
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

@dataclass
class ContactInfo:
    """Represents contact information extracted from a VCF file"""
    full_name: str
    phone_numbers: List[str]
    emails: List[str]
    addresses: List[str]
    organization: Optional[str] = None
    title: Optional[str] = None
    photo: Optional[bytes] = None

class VCFHandler:
    """Handles parsing of VCF (vCard) files from WhatsApp exports"""
    
    @staticmethod
    def parse_vcf_file(file_path: str) -> ContactInfo:
        """Parse a VCF file and return structured contact information"""
        with open(file_path, 'r', encoding='utf-8') as f:
            vcard = vobject.readOne(f.read())
            
        # Extract basic info
        full_name = str(vcard.fn.value) if hasattr(vcard, 'fn') else "Unknown"
        
        # Extract phone numbers
        phone_numbers = []
        if hasattr(vcard, 'tel'):
            if isinstance(vcard.tel, list):
                phone_numbers = [tel.value for tel in vcard.tel]
            else:
                phone_numbers = [vcard.tel.value]
                
        # Extract emails
        emails = []
        if hasattr(vcard, 'email'):
            if isinstance(vcard.email, list):
                emails = [email.value for email in vcard.email]
            else:
                emails = [vcard.email.value]
                
        # Extract addresses
        addresses = []
        if hasattr(vcard, 'adr'):
            if isinstance(vcard.adr, list):
                for adr in vcard.adr:
                    if hasattr(adr, 'value'):
                        # Join address components, filtering out empty parts
                        addr_parts = [p for p in adr.value if p]
                        if addr_parts:
                            addresses.append(', '.join(addr_parts))
            elif hasattr(vcard.adr, 'value'):
                addr_parts = [p for p in vcard.adr.value if p]
                if addr_parts:
                    addresses.append(', '.join(addr_parts))
        
        # Extract organization
        organization = None
        if hasattr(vcard, 'org'):
            org_value = vcard.org.value
            if isinstance(org_value, list):
                organization = ' '.join(org_value)
            else:
                organization = str(org_value)
                
        # Extract title
        title = str(vcard.title.value) if hasattr(vcard, 'title') else None
        
        # Extract photo if present
        photo = None
        if hasattr(vcard, 'photo'):
            try:
                photo = vcard.photo.value
            except:
                pass  # Ignore photo extraction errors
                
        return ContactInfo(
            full_name=full_name,
            phone_numbers=phone_numbers,
            emails=emails,
            addresses=addresses,
            organization=organization,
            title=title,
            photo=photo
        )
