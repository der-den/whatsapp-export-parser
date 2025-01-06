# Additional Requirements for WhatsApp Export Parser

## Font Requirements

The WhatsApp Export Parser requires Unicode-compatible fonts to properly display emojis and special characters in the generated PDFs. The script will try to use fonts in the following order:

1. Noto Color Emoji (required for emoji support)
2. DejaVu Sans (for general Unicode support)
3. Liberation Sans (fallback)
4. Helvetica (basic fallback, limited Unicode support)

### Installing Fonts

#### Arch Linux
```bash
# Install Noto Emoji fonts (required for emoji support)


# Install DejaVu fonts
sudo pacman -S ttf-dejavu

# OR install Liberation fonts
sudo pacman -S ttf-liberation

# After installation, update font cache
sudo fc-cache -f -v

# Verify font installation
fc-list | grep -i noto
fc-list | grep -i dejavu
```

#### Ubuntu/Debian
```bash
# Install Noto Emoji fonts (required for emoji support)
sudo apt-get install fonts-noto-color-emoji

# Install DejaVu fonts
sudo apt-get install fonts-dejavu

# OR install Liberation fonts
sudo apt-get install fonts-liberation

# After installation, update font cache
sudo fc-cache -f -v

# Verify font installation
fc-list | grep -i noto
fc-list | grep -i dejavu
```

### After Font Installation

After installing new fonts, you need to:

1. Update the font cache:
   ```bash
   sudo fc-cache -f -v
   ```

2. Either:
   - Start a new terminal session
   - OR reload your shell:
   ```bash
   exec $SHELL
   ```

3. Verify the fonts are available:
   ```bash
   # Check for Noto Emoji font
   fc-list | grep -i "noto.*emoji"
   
   # Check font paths
   fc-match -v NotoColorEmoji
   ```

If you don't see the fonts listed, try:
1. Logging out and back in
2. Or as a last resort, restarting your system

#### Font Locations

The script looks for fonts in these default locations:

- Noto Color Emoji:
  - `/usr/share/fonts/noto/NotoColorEmoji.ttf`
  - `/usr/share/fonts/google-noto/NotoColorEmoji.ttf`
  - `/usr/share/fonts/noto-cjk/NotoColorEmoji.ttf`
- DejaVu Sans:
  - `/usr/share/fonts/TTF/DejaVuSans.ttf` (Arch Linux)
  - `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` (Ubuntu/Debian)
- Liberation Sans:
  - `/usr/share/fonts/TTF/LiberationSans-Regular.ttf` (Arch Linux)
  - `/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf` (Ubuntu/Debian)

If your system has the fonts installed in different locations, you may need to modify the paths in the script.

## Unicode Support

The script is designed to handle:
- Emojis from WhatsApp messages (requires Noto Color Emoji font)
- Special characters in usernames
- International characters
- Attachment symbols

Without the Noto Color Emoji font, emojis may appear as boxes (□) or question marks (?) in the PDF output.

## PDF Features

The generated PDFs will include:
- All Unicode characters from the original chat
- Emoji display (with Noto Color Emoji font)
- Attachment indicators (📎)
- Time stamps in either 24-hour (default) or 12-hour format

## Command Line Options

Use the following options to customize the output:
```bash
python whatsapp_export_parser.py chat.zip --12h     # Use 12-hour time format
python whatsapp_export_parser.py chat.zip --debug   # Show debug information
python whatsapp_export_parser.py chat.zip --keep-temp # Keep temporary files
