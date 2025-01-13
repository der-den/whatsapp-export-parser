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
    'errors': {
        'invalid_language': 'Ungültiger Sprachcode. Unterstützte Sprachen sind: {}',
        'file_not_found': 'Datei nicht gefunden: {}',
        'transcription_failed': 'Audio-Transkription fehlgeschlagen: {}'
    }
}
