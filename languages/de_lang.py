#!/usr/bin/env python3

"""German language strings"""

LANG_STRINGS = {
    'pdf': {
        'header': {
            'timestamp': 'Erstellt am',
            'filename': 'Datei',
            'device_owner': 'Gerätebesitzer'
        },
        'audio': {
            'duration': 'Dauer',
            'size': 'Größe',
            'transcription': 'Transkription',
            'transcription_warning': 'Hinweis: Diese Transkription wurde von KI erstellt und ist möglicherweise nicht 100% genau.'
        },
        'attachments': {
            'image': 'Bildanhang',
            'video': 'Videoanhang',
            'audio': 'Audioanhang',
            'document': 'Dokumentanhang'
        },
        'statistics': {
            'title': 'Chat-Statistiken',
            'total_messages': 'Gesamtnachrichten',
            'participants': 'Teilnehmer',
            'date_range': 'Zeitraum'
        }
    },
    'statistics': {
        'title': 'Chat-Statistiken',
        'total_messages': 'Gesamtnachrichten',
        'edited_messages': 'Bearbeitete Nachrichten',
        'multiframe_content': 'Mehrrahmeninhalt',
        'missing_attachments': 'Fehlende Anhänge',
        'messages_by_sender': 'Nachrichten nach Absender',
        'messages_by_type': 'Nachrichten nach Typ',
        'preview_title': 'Vorschau-Statistiken'
    },
    'info': {
        'using_first_sender': 'Kein Gerätebesitzer angegeben, verwende ersten Absender: {}',
        'processing_meta': 'Verarbeite Meta-Informationen',
        'pdf_generated': 'PDF erstellt: {}',
        'total_messages_processed': 'Verarbeitete Nachrichten insgesamt: {}',
        'chat_members': 'Chat-Teilnehmer: {}'
    },
    'debug': {
        'enabled': 'Debug-Ausgabe aktiviert'
    },
    'errors': {
        'file_not_found': 'Datei nicht gefunden: {}',
        'zip_error': 'ZIP-Fehler: {}',
        'general': 'Fehler: {}'
    },
    'argparse': {
        'description': 'WhatsApp-Chat-Export in PDF konvertieren',
        'input': 'Eingabedateipfad (ZIP oder TXT)',
        'debug': 'Debug-Ausgabe aktivieren',
        'device_owner': 'Name des Gerätebesitzers im Chat',
        'output': 'Ausgabeverzeichnispfad (optional)',
        'headertext': 'Benutzerdefinierter Text für die Kopfzeile jeder Seite',
        'footertext': 'Benutzerdefinierter Text für die Fußzeile jeder Seite',
        'zip_stats_only': 'Nur ZIP-Statistiken anzeigen und beenden',
        'stats_only': 'Nur Statistiken über den Chat-Inhalt anzeigen und beenden',
        'no_attachments': 'Keine Anhänge in den PDF-Bericht aufnehmen',
        'app_lang': 'Anwendungssprache (überschreibt Konfigurationseinstellung)',
        'content_lang': 'Chat-Inhaltssprache (überschreibt Konfigurationseinstellung)'
    }
}
