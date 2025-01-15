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

# Global language variables
app_lang = None
content_lang = None

def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return False

def parse_args():
    # Use the global language for argument parsing
    global app_lang
    
    parser = argparse.ArgumentParser(description=app_lang.get('argparse', 'description'))
    parser.add_argument('input', help=app_lang.get('argparse', 'input'))
    parser.add_argument('--debug', action='store_true', help=app_lang.get('argparse', 'debug'))
    parser.add_argument('--device-owner', help=app_lang.get('argparse', 'device_owner'))
    parser.add_argument('--output', help=app_lang.get('argparse', 'output'))
    parser.add_argument('--headertext', help=app_lang.get('argparse', 'headertext'))
    parser.add_argument('--footertext', help=app_lang.get('argparse', 'footertext'))
    parser.add_argument('--zip-stats-only', action='store_true', help=app_lang.get('argparse', 'zip_stats_only'))
    parser.add_argument('--stats-only', action='store_true', help=app_lang.get('argparse', 'stats_only'))
    parser.add_argument('-na', '--no-attachments', action='store_true', help=app_lang.get('argparse', 'no_attachments'))
    parser.add_argument('--app-lang', type=str, help=app_lang.get('argparse', 'app_lang'))
    parser.add_argument('--content-lang', type=str, help=app_lang.get('argparse', 'content_lang'))
    
    return parser.parse_args()

def main():
    # Load config first to get default language settings
    config = load_config()
    if config is False:
        print("Error: config.json not found")
        return 1
        
    # Initialize global languages with defaults from config
    global app_lang, content_lang
    app_lang = load_language(config["language"]["application"])
    content_lang = load_language(config["language"]["chat_content"])

    # Now parse args (which will use app_lang)
    args = parse_args()
    
    # Override languages if specified in command line args
    if args.app_lang:
        app_lang = load_language(args.app_lang)
    if args.content_lang:
        content_lang = load_language(args.content_lang)

    # read app version number from file 'version'
    with open('version', 'r') as f:
        version = f.read().strip()
    
    # Print application info
    print(f"Whatsapp Chat Export to PDF, v{version}")
    print('==========================')
    print(f"Application language: {app_lang.name}")
    print(f"Chat content language: {content_lang.name}")

    # Enable debug output if requested
    debug_enabled = False
    if args.debug:
        debug_enabled = True
        print(app_lang.get('debug', 'enabled'))

        # Make sure debug is enabled in utils and initialize debug file
        utils.DEBUG = True
        utils.init_debug_file(args.input)

    try:
        # Initialize ZIP handler if input is a ZIP file
        zip_handler = None
        if args.input.lower().endswith('.zip'):
            try:
                zip_handler = ZipHandler(args.input, app_lang)
                
                
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
                
            # Extract ZIP contents
            try:
                zip_handler.unpack_zip()
            except ValueError as e:
                print(app_lang.get('errors', 'extraction_failed').format(str(e)))
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on error
                return 1

            # Find chat file
            chat_file = zip_handler.find_chat_file()
            if not chat_file:
                print(app_lang.get('errors', 'no_chat_file'))
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on error
                return 1
        
            
            if args.zip_stats_only:
                if debug_enabled:
                    utils.close_debug_file()  # Close debug file on exit
                return 0
            
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
            print(app_lang.get('info', 'using_first_sender').format(args.device_owner))
            
        # Get and display statistics
        stats = chat_parser.get_statistics()
        
        # Always show statistics
        print(f"\n{app_lang.get('statistics', 'title')}:")
        print(f"{app_lang.get('statistics', 'total_messages')}: {stats.total_messages}")
        print(f"{app_lang.get('statistics', 'edited_messages')}: {stats.edited_messages}")
        print(f"{app_lang.get('statistics', 'multiframe_content')}: {stats.multiframe_count}")
        print(f"{app_lang.get('statistics', 'missing_attachments')}: {stats.missing_attachments}")
        print(f"\n{app_lang.get('statistics', 'messages_by_sender')}:")
        for sender, count in stats.messages_by_sender.most_common():
            print(f"  {sender}: {count}")
        print(f"\n{app_lang.get('statistics', 'messages_by_type')}:")
        for type_, count in stats.messages_by_type.most_common():
            print(f"  {type_.name}: {count}")
        
        if args.stats_only:
            if debug_enabled:
                utils.close_debug_file()  # Close debug file on exit
            return 0
            
        utils.debug_print("\n\n\n=== Processing meta information ===\n\n\n")

        # Process meta information (video previews, screenshots)
        print(f"\n{app_lang.get('info', 'processing_meta')}...")
        meta_parser = MetaParser(zip_handler)
        preview_stats = meta_parser.process_messages(messages, ChatParser.URL_PATTERN)
        
        # Show preview statistics
        print(f"\n{app_lang.get('statistics', 'preview_title')}:")
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
        
        utils.debug_print("\n\n\n=== Generating PDF ===\n\n\n")

        # Generate PDF
        zip_size = os.path.getsize(args.input) if os.path.exists(args.input) else None
        zip_md5 = zip_handler.md5_hash if zip_handler else None
        
        pdf_generator = PDFGenerator(output_path, args.device_owner, 
                                   zip_handler.extract_path if zip_handler else None, 
                                   args.headertext, args.footertext, args.input,
                                   zip_size, zip_md5, args.no_attachments,
                                   config=config)  # Pass config to PDFGenerator
        pdf_generator.generate_pdf(messages, chat_parser.chat_members, stats)
        
        print(f"{app_lang.get('info', 'pdf_generated')}: {output_path}")
        print(f"{app_lang.get('info', 'total_messages_processed')}: {len(messages)}")
        print(f"{app_lang.get('info', 'chat_members')}: {', '.join(sorted(chat_parser.chat_members))}")
        
        # Clean up extracted files if we used a ZIP
        zip_handler.cleanup()  # Show stats and cleanup files
            
        if debug_enabled:
            utils.close_debug_file()  # Close debug file before exiting
        return 0
        
    except KeyboardInterrupt:
        print(app_lang.get('errors', 'interrupted'))
        if debug_enabled:
            utils.close_debug_file()  # Close debug file on interrupt
        return 1
    except Exception as e:
        if debug_enabled:
            import traceback
            traceback.print_exc()
        
        print(app_lang.get('errors', 'general').format(str(e)))
        
        if debug_enabled:
            utils.close_debug_file()  # Close debug file on error
        return 1

if __name__ == '__main__':
    exit(main())
