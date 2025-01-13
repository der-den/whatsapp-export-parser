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
        'zip_error': 'Fehler beim Verarbeiten der ZIP-Datei: {}',
        'general': 'Ein Fehler ist aufgetreten: {}',
        'no_chat_file': 'Keine Chat-Datei im ZIP-Archiv gefunden',
        'extraction_failed': 'Fehler beim Extrahieren des ZIP-Archivs: {}',
        'no_messages_found': 'Keine Nachrichten in der Chat-Datei gefunden',
        'interrupted': 'Vorgang vom Benutzer unterbrochen'
    }
}
