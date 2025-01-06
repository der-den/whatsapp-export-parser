import emoji
from utils import debug_print

def process_emojis(text: str) -> str:
    """Convert emoji to their text representation for better PDF support"""
    try:
        # Replace emojis with their text representation
        text = emoji.demojize(text)
        debug_print(f"Processed text with emojis: {text}")
        return text
    except Exception as e:
        debug_print(f"Error converting emoji: {str(e)}")
        return text
