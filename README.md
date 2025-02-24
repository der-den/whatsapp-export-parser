# WhatsApp Export Parser

This Python script takes your WhatsApp Export ZIP file, parses the included text file, and builds a PDF report.

## Features

- Generates a main PDF for the chat and separate PDFs for each attachment
- Optimized for German exports (basic language support for other languages is in progress)
- Processes various types of attachments:
  - Images: Resized and embedded in the report
  - Videos: Extracts and adds 4 frames to the report
  - Audio: Optional transcription using Whisper AI
  - Stickers: Embedded as images (up to 9 frames for multi-frame stickers in attachment PDFs)

## Requirements

- Python 3.10.x
- Virtual environment (recommended)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/der-den/whatsapp-export-parser.git
   cd whatsapp-export-parser
   ```

2. Create and activate a virtual environment:
   ```bash
   python3.10 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Dependencies

Key packages:
- reportlab: PDF generation
- Pillow: Image processing
- torch & openai-whisper: Audio transcription
- opencv-python: Video frame extraction
- Other utilities: emoji, mutagen, vobject

All dependencies are specified in `requirements.txt` with their respective versions.
