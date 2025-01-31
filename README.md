This Python script take your WhatsApp Export ZIP file, parse the included text file and build a PDF report.

- At time the script building one PDF for the chat and for each attachment a extra pdf.
- At time the script is optimized for german exports! A basic language support is started but not full implemented.  

Embedding attachments in the report:
All attachments comes with informations for name, size, duration, sender, md5, attachment number 

- pictures are resized and added
- take video frames and add 4 frames to the report
- audio files can optionaly passed to whisper and direct transcoded to text
- stickers are included with one image to the pdf, in the attachment pdf are up to 9 frames for multi-frame stickers
-  
