#!/usr/bin/env python3

import warnings
import argparse
import os
import sys
import json
from pathlib import Path
from zip_handler import ZipHandler
from chat_parser import ChatParser
from pdf_generator import PDFGenerator
from meta_parser import MetaParser
from languages import load_language, DEFAULT_LANGUAGE
import utils

def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "audio": {
                "transcription_enabled": True,
                "whisper_model": "medium"
            },
            "output": {
                "include_attachments": True,
                "max_image_width": 800,
                "max_image_height": 600
            },
            "language": {
                "application": DEFAULT_LANGUAGE,
                "chat_content": DEFAULT_LANGUAGE
            }
        }

def parse_args():
    parser = argparse.ArgumentParser(description='Convert WhatsApp chat export to PDF')
    parser.add_argument('input', help='Input file path (ZIP or TXT)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--device-owner', help='Name of the device owner in the chat')
    parser.add_argument('--output', help='Output directory path (optional)')
    parser.add_argument('--headertext', help='Custom text for the header of each page')
    parser.add_argument('--footertext', help='Custom text for the footer of each page')
    parser.add_argument('--zip-stats-only', action='store_true', help='Only print ZIP stats and exit')
    parser.add_argument('--stats-only', action='store_true', help='Only print statistics and exit')
    parser.add_argument('-na', '--no-attachments', action='store_true', help='Do not include attachments in the PDF report')
    parser.add_argument('--app-lang', type=str, help='Application language (overrides config setting)')
    parser.add_argument('--content-lang', type=str, help='Chat content language (overrides config setting)')
    
    return parser.parse_args()

def main():
    args = parse_args()
    config = load_config()
    
    # Load language settings (command line args override config)
    app_lang = load_language(args.app_lang if args.app_lang else config["language"]["application"])
    content_lang = load_language(args.content_lang if args.content_lang else config["language"]["chat_content"])
    
    # Enable debug output if requested
    debug_enabled = False
    if args.debug:
        debug_enabled = True
        print("Debug output enabled")

        # Make sure debug is enabled in utils and initialize debug file
        utils.DEBUG = True
        utils.init_debug_file(args.input)

    try:
        # Initialize ZIP handler if input is a ZIP file
        zip_handler = None
        if args.input.lower().endswith('.zip'):
            try:
                zip_handler = ZipHandler(args.input)
                
                # Print ZIP stats if requested
                zip_handler.print_stats()
            except FileNotFoundError as e:
                print(app_lang.get('errors', 'file_not_found').format(str(e)))
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on error
                return 1
            except ValueError as e:
                print(app_lang.get('errors', 'zip_error').format(str(e)))
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on error
                return 1
            except Exception as e:
                if debug_enabled:
                    import traceback
                    traceback.print_exc()
                print(app_lang.get('errors', 'general').format(str(e)))
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on error
                return 1
                
            if not zip_handler.chat_file:
                print(app_lang.get('errors', 'no_chat_file'))
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on error
                return 1
                
            # Extract chat file path
            chat_file = zip_handler.chat_file
            
            if args.zip_stats_only:
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on exit
                return 0
            
            # Extract ZIP contents
            try:
                zip_handler.extract()
            except ValueError as e:
                print(app_lang.get('errors', 'extraction_failed').format(str(e)))
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on error
                return 1

        import utils
        utils.debug_print("\n\n\n=== Parsing chat file ===\n\n\n")

        # Initialize parser and parse messages
        chat_parser = ChatParser(zip_handler, args.device_owner)
        messages = chat_parser.parse_chat_file()
        
        if not messages:
            print(app_lang.get('errors', 'no_messages_found'))
            if debug_enabled:
                utils.close_debug_file()  # Close debug file on error
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
            if debug_enabled:
                utils.close_debug_file()  # Close debug file on exit
            return 0
            
        import utils
        utils.debug_print("\n\n\n=== Processing meta information ===\n\n\n")

        # Process meta information (video previews, screenshots)
        print("\nProcessing meta information...")
        meta_parser = MetaParser(zip_handler)
        preview_stats = meta_parser.process_messages(messages, ChatParser.URL_PATTERN)
        
        # Show preview statistics
        print("\nPreview Statistics:")
        for content_type, count in preview_stats.items():
            total = stats.messages_by_type[content_type]
            #success_rate = (count/total)*100 if total > 0 else 0
            print(f"  {content_type.name}: {count}")
            
        # for test only, no pdf generation
        #return 0

        # Determine output path for pdf creation
        if args.output:
            output_path = str(Path(args.output) / f"{Path(args.input).stem}.pdf")
        else:
            input_path = Path(args.input)
            output_path = str(input_path.with_suffix('.pdf'))
        
        import utils
        utils.debug_print("\n\n\n=== Generating PDF ===\n\n\n")

        # Generate PDF
        zip_size = os.path.getsize(args.input) if os.path.exists(args.input) else None
        zip_md5 = zip_handler.md5_hash if zip_handler else None
        
        pdf_generator = PDFGenerator(output_path, args.device_owner, 
                                   zip_handler.extract_path if zip_handler else None, 
                                   args.headertext, args.footertext, args.input,
                                   zip_size, zip_md5, args.no_attachments)
        pdf_generator.generate_pdf(messages, chat_parser.chat_members, stats)
        
        print(f"PDF generated: {output_path}")
        print(f"Total messages processed: {len(messages)}")
        print(f"Chat members: {', '.join(sorted(chat_parser.chat_members))}")

        # remove extracted files
        if zip_handler:
            if args.debug:
                zip_handler.show_statistics()  # Show stats in debug mode
            else:
                zip_handler.cleanup()  # Show stats and cleanup files

        if debug_enabled:
            import utils
            utils.close_debug_file()  # Close debug file before exiting
        return 0
        
    except Exception as e:
        print(app_lang.get('errors', 'general').format(str(e)))
        if args.debug:
            import traceback
            traceback.print_exc()
        if debug_enabled:
            import utils
            utils.close_debug_file()  # Close debug file on error
        return 1

if __name__ == '__main__':
    exit(main())
