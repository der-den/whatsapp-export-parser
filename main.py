#!/usr/bin/env python3

import argparse
from pathlib import Path
from zip_handler import ZipHandler
from chat_parser import ChatParser
from pdf_generator import PDFGenerator
from utils import debug_print, DEBUG
from meta_parser import MetaParser
import os

def parse_args():
    parser = argparse.ArgumentParser(description='Convert WhatsApp chat export to PDF')
    parser.add_argument('input', help='Path to WhatsApp chat export file (_chat.txt or .zip)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--device-owner', help='Name of the device owner in the chat')
    parser.add_argument('--output', help='Output directory path (optional)')
    parser.add_argument('--headertext', help='Custom text for the header of each page')
    parser.add_argument('--footertext', help='Custom text for the footer of each page')
    parser.add_argument('--zip-stats-only', action='store_true', help='Only print ZIP stats and exit')
    parser.add_argument('--stats-only', action='store_true', help='Only print statistics and exit')
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Enable debug output if requested
    if args.debug:
        global DEBUG
        DEBUG = True
    
    try:
        print(f"Processing file: {args.input}")
        
        # Initialize handlers
        if args.input.endswith('.zip'):
            zip_handler = ZipHandler(args.input)
        else:
            zip_handler = None
        
        # Get ZIP info first
        if zip_handler:
            try:
                zip_info = zip_handler.get_zip_info()
            except FileNotFoundError as e:
                print(f"Error: {str(e)}")
                return 1
            except ValueError as e:
                print(f"Error: {str(e)}")
                return 1
            except Exception as e:
                print(f"Unexpected error reading ZIP file: {str(e)}")
                if args.debug:
                    import traceback
                    traceback.print_exc()
                return 1
                
            if not zip_info:
                print("Error: Could not read ZIP file information")
                return 1
                
            # Print ZIP stats
            print("\nZIP File Information:")
            print(f"Name: {zip_info['name']}")
            print(f"Size: {zip_info['size']}")
            print(f"Date: {zip_info['date']}")
            print(f"MD5: {zip_info['md5']}")
            print(f"Content Count: {zip_info['content_count']}")
            
            if args.zip_stats_only:
                return 0
            
            # Extract ZIP contents
            try:
                extract_path = zip_handler.unpack_zip()
                print(f"\nExtracted to: {extract_path}")
            except ValueError as e:
                print(f"Error extracting ZIP: {str(e)}")
                return 1
                
        # Initialize parser and parse messages
        chat_parser = ChatParser(zip_handler, args.device_owner)
        messages = chat_parser.parse_chat_file()
        
        if not messages:
            print("Error: No messages found in chat file")
            return 1
            
        # If no device owner specified, use the sender of the first message
        if not args.device_owner and messages:
            args.device_owner = messages[0].sender
            print(f"No device owner specified, using first sender: {args.device_owner}")
            
        # Get and display statistics
        stats = chat_parser.get_statistics()
        
        # Always show statistics
        print("\nChat Statistics:")
        print(f"Total Messages: {stats.total_messages}")
        print(f"Edited Messages: {stats.edited_messages}")
        print(f"Multiframe Content: {stats.multiframe_count}")
        print(f"Missing Attachments: {stats.missing_attachments}")
        print(f"\nMessages by Sender:")
        for sender, count in stats.messages_by_sender.most_common():
            print(f"  {sender}: {count}")
        print(f"\nMessages by Type:")
        for type_, count in stats.messages_by_type.most_common():
            print(f"  {type_.name}: {count}")
        
        if args.stats_only:
            return 0
            
        # Process meta information (video previews, screenshots)
        print("\nProcessing meta information...")
        meta_parser = MetaParser(zip_handler)
        preview_stats = meta_parser.process_messages(messages, ChatParser.URL_PATTERN)
        
        # Show preview statistics
        print("\nPreview Statistics:")
        for content_type, count in preview_stats.items():
            total = stats.messages_by_type[content_type]
            success_rate = (count/total)*100 if total > 0 else 0
            print(f"  {content_type.name}: {count}/{total} ({success_rate:.1f}%)")
            
        # Determine output path for pdf creation
        if args.output:
            output_path = str(Path(args.output) / f"{Path(args.input).stem}.pdf")
        else:
            input_path = Path(args.input)
            output_path = str(input_path.with_suffix('.pdf'))
        
        # Generate PDF
        zip_size = os.path.getsize(args.input) if os.path.exists(args.input) else None
        zip_md5 = zip_handler.md5_hash if zip_handler else None
        
        pdf_generator = PDFGenerator(output_path, args.device_owner, 
                                   zip_handler.extract_path if zip_handler else None, 
                                   args.headertext, args.footertext, args.input,
                                   zip_size, zip_md5)
        pdf_generator.generate_pdf(messages, chat_parser.chat_members, stats)
        
        print(f"PDF generated: {output_path}")
        print(f"Total messages processed: {len(messages)}")
        print(f"Chat members: {', '.join(sorted(chat_parser.chat_members))}")

        # remove extracted files
        if zip_handler and not args.debug:
            zip_handler.cleanup()

        return 0
        
    except Exception as e:
        print(f"Error: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit(main())
