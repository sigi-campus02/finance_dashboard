# plants/management/commands/bulk_upload_photos.py

from django.core.management.base import BaseCommand
from django.core.files import File
from django.contrib.auth.models import User
from django.utils import timezone
from pathlib import Path
from datetime import datetime
import re
import json

from plants.models import Plant, PlantImage, PlantGroup


class Command(BaseCommand):
    help = 'Lädt mehrere Pflanzenfotos mit automatischer Gruppen- und Pflanzenzuordnung'

    def add_arguments(self, parser):
        parser.add_argument(
            'path',
            type=str,
            help='Pfad zum Ordner mit Bildern oder einzelne Bild-Datei'
        )
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help='Username für Zuordnung (falls mehrere User)'
        )
        parser.add_argument(
            '--group-mapping',
            type=str,
            default='plant_groups_mapping.json',
            help='Pfad zur JSON-Datei mit Gruppen-Zuordnung'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Nur Analyse, keine Uploads'
        )
        parser.add_argument(
            '--create-missing',
            action='store_true',
            help='Erstellt fehlende Pflanzen automatisch'
        )
        parser.add_argument(
            '--case-insensitive',
            action='store_true',
            default=True,
            help='Ignoriert Groß-/Kleinschreibung bei Pflanzennamen (Standard: aktiv)'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.create_missing = options['create_missing']
        self.case_insensitive = options['case_insensitive']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🌱 Bulk Upload Pflanzenfotos mit Gruppen'))
        self.stdout.write('=' * 70)

        # User ermitteln
        user = self._get_user(options.get('user'))
        if not user:
            return

        self.stdout.write(f'\n👤 User: {user.username}')

        # Gruppen-Mapping laden
        group_mapping_file = options['group_mapping']
        self.group_mapping = self._load_group_mapping(group_mapping_file)
        if self.group_mapping is None:
            self.stdout.write(self.style.WARNING(
                f'\n⚠️  Keine Gruppen-Mapping-Datei gefunden: {group_mapping_file}'
                '\n   Fahre ohne Gruppen fort...'
            ))
            self.group_mapping = {'groups': {}, 'plants_without_group': []}
        else:
            self.stdout.write(self.style.SUCCESS(
                f'📋 Gruppen-Mapping geladen: {len(self.group_mapping["groups"])} Gruppen'
            ))

        # Pfad validieren
        source_path = Path(options['path'])
        if not source_path.exists():
            self.stdout.write(self.style.ERROR(f'\n❌ Pfad nicht gefunden: {options["path"]}'))
            return

        # Bilder sammeln
        image_files = self._collect_images(source_path)
        if not image_files:
            self.stdout.write(self.style.WARNING(f'\n⚠️  Keine Bilder gefunden in: {options["path"]}'))
            return

        self.stdout.write(f'📁 Quelle: {source_path}')
        self.stdout.write(f'🖼️  Gefunden: {len(image_files)} Bilder')

        if self.dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  DRY RUN - Keine Änderungen werden gespeichert!\n'))

        # Caches vorladen
        self._init_caches(user)

        # Verarbeitung
        stats = {
            'success': 0,
            'skipped': 0,
            'errors': 0,
            'created_plants': 0,
            'created_groups': 0
        }

        for idx, image_file in enumerate(image_files, 1):
            self.stdout.write(f'\n[{idx:3d}/{len(image_files)}] {image_file.name}')

            result = self._process_image(image_file, user)

            if result['status'] == 'success':
                stats['success'] += 1
                if result.get('plant_created'):
                    stats['created_plants'] += 1
                if result.get('group_created'):
                    stats['created_groups'] += 1
                self.stdout.write(self.style.SUCCESS(f'  ✅ {result["message"]}'))
            elif result['status'] == 'skipped':
                stats['skipped'] += 1
                self.stdout.write(self.style.WARNING(f'  ⊘ {result["message"]}'))
            else:
                stats['errors'] += 1
                self.stdout.write(self.style.ERROR(f'  ❌ {result["message"]}'))

        # Zusammenfassung
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('📊 Zusammenfassung'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n✅ Erfolgreich: {stats["success"]}')
        if stats['created_groups'] > 0:
            self.stdout.write(f'🏷️  Gruppen erstellt: {stats["created_groups"]}')
        if stats['created_plants'] > 0:
            self.stdout.write(f'🆕 Pflanzen erstellt: {stats["created_plants"]}')
        self.stdout.write(f'⊘  Übersprungen: {stats["skipped"]}')
        self.stdout.write(f'❌ Fehler: {stats["errors"]}')
        self.stdout.write(f'\n📝 Total: {len(image_files)} Bilder')

    def _get_user(self, username):
        """Ermittelt User für Upload"""
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'\n❌ User "{username}" nicht gefunden!'))
                return None

        user_count = User.objects.count()
        if user_count == 0:
            self.stdout.write(self.style.ERROR('\n❌ Keine User in Datenbank!'))
            return None
        elif user_count == 1:
            return User.objects.first()
        else:
            self.stdout.write(self.style.ERROR(
                f'\n❌ {user_count} User gefunden! Bitte --user angeben:\n'
            ))
            for user in User.objects.all():
                self.stdout.write(f'   - {user.username}')
            return None

    def _load_group_mapping(self, filepath):
        """Lädt Gruppen-Mapping aus JSON-Datei"""
        path = Path(filepath)
        if not path.exists():
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validiere Struktur
            if 'groups' not in data:
                self.stdout.write(self.style.ERROR(
                    f'\n❌ Ungültige Mapping-Datei: "groups" Schlüssel fehlt!'
                ))
                return None

            # Erstelle umgekehrtes Mapping: plant_name -> group_name
            self.plant_to_group = {}
            for group_name, plants in data['groups'].items():
                for plant in plants:
                    # Case-insensitive Mapping
                    key = plant.lower() if self.case_insensitive else plant
                    self.plant_to_group[key] = group_name

            # Pflanzen ohne Gruppe auch mappen
            if 'plants_without_group' in data:
                for plant in data['plants_without_group']:
                    key = plant.lower() if self.case_insensitive else plant
                    self.plant_to_group[key] = None

            return data

        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(
                f'\n❌ JSON-Fehler in {filepath}: {e}'
            ))
            return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'\n❌ Fehler beim Laden von {filepath}: {e}'
            ))
            return None

    def _init_caches(self, user):
        """Initialisiert Caches für schnellere Zuordnung"""
        # Pflanzen-Cache
        self.plants_cache = {
            plant.name.lower(): plant
            for plant in Plant.objects.filter(user=user).select_related('group')
        }

        # Gruppen-Cache
        self.groups_cache = {
            group.name.lower(): group
            for group in PlantGroup.objects.filter(user=user)
        }

        self.stdout.write(f'🌿 Vorhandene Pflanzen: {len(self.plants_cache)}')
        self.stdout.write(f'🏷️  Vorhandene Gruppen: {len(self.groups_cache)}\n')

    def _collect_images(self, path: Path):
        exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic'}
        if path.is_file():
            return [path] if path.suffix.lower() in exts else []

        images = {p.resolve() for ext in exts for p in path.glob(f'*{ext}')}
        return sorted(images, key=lambda p: p.name.lower())

    def _process_image(self, image_file, user):
        """Verarbeitet ein einzelnes Bild"""
        try:
            # Dateinamen parsen: pflanze_JJJJMMTT_NN.jpg
            parsed = self._parse_filename(image_file.stem)

            if not parsed:
                return {
                    'status': 'error',
                    'message': f'Ungültiges Format: "{image_file.name}" (Erwartet: pflanze_JJJJMMTT[_NN].jpg)'
                }

            plant_name = parsed['plant_name']
            captured_date = parsed['date']

            # Gruppe ermitteln (aus Mapping)
            group_name = self._get_group_for_plant(plant_name)

            # Gruppe erstellen/finden falls nötig
            group = None
            group_created = False
            if group_name:
                group_result = self._get_or_create_group(group_name, user)
                group = group_result['group']
                group_created = group_result.get('created', False)

            # Pflanze finden oder erstellen
            plant_result = self._get_or_create_plant(plant_name, user, group)

            if not plant_result['plant']:
                return {
                    'status': 'skipped',
                    'message': f'Pflanze "{plant_name}" nicht gefunden (nutze --create-missing)'
                }

            plant = plant_result['plant']
            plant_created = plant_result.get('created', False)

            # Prüfe ob Bild bereits existiert
            existing = PlantImage.objects.filter(
                plant=plant,
                image__icontains=image_file.name
            ).exists()

            if existing and not self.dry_run:
                return {
                    'status': 'skipped',
                    'message': f'{plant.name} - Datei "{image_file.name}" bereits vorhanden'
                }

            # Upload durchführen
            if not self.dry_run:
                with open(image_file, 'rb') as f:
                    plant_image = PlantImage(
                        plant=plant,
                        captured_at=captured_date
                    )
                    plant_image.image.save(
                        image_file.name,
                        File(f),
                        save=True
                    )

            # Message mit Gruppen-Info
            group_info = f" [{group_name}]" if group_name else ""
            message = f'{plant.name}{group_info} am {captured_date.strftime("%d.%m.%Y")}'

            return {
                'status': 'success',
                'message': message,
                'plant_created': plant_created,
                'group_created': group_created
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Fehler: {str(e)}'
            }

    def _parse_filename(self, filename):
        """
        Parst Dateinamen im Format: pflanze_JJJJMMTT oder pflanze_JJJJMMTT_NN

        Beispiele:
        - AvokadoErde_20251029 -> plant_name="AvokadoErde", date=2025-10-29
        - PetersilieAfrodite_20251029_01 -> plant_name="PetersilieAfrodite", date=2025-10-29
        - BasilikumChianti_Anzucht_20241215_02 -> plant_name="BasilikumChianti_Anzucht", date=2024-12-15
        """
        # Pattern: pflanze_JJJJMMTT mit optionalem Suffix _NN
        pattern = r'^(.+?)_(\d{8})(?:_\d+)?$'
        match = re.match(pattern, filename)

        if not match:
            return None

        plant_name_raw = match.group(1)
        date_str = match.group(2)

        # Pflanzenname: KEINE Transformation mehr (behält _ bei)
        # z.B. "BasilikumChianti_Anzucht" bleibt "BasilikumChianti_Anzucht"
        plant_name = plant_name_raw.strip()

        # Datum parsen
        try:
            date_obj = datetime.strptime(date_str, '%Y%m%d')
            date_aware = timezone.make_aware(date_obj, timezone.get_current_timezone())
        except ValueError:
            return None

        return {
            'plant_name': plant_name,
            'date': date_aware
        }

    def _get_group_for_plant(self, plant_name):
        """Ermittelt Gruppenname für Pflanze aus Mapping"""
        if not self.group_mapping:
            return None

        search_key = plant_name.lower() if self.case_insensitive else plant_name

        return self.plant_to_group.get(search_key, None)

    def _get_or_create_group(self, group_name, user):
        """Findet Gruppe oder erstellt sie"""
        search_name = group_name.lower() if self.case_insensitive else group_name

        # Im Cache suchen
        if search_name in self.groups_cache:
            return {
                'group': self.groups_cache[search_name],
                'created': False
            }

        # In Datenbank suchen
        if self.case_insensitive:
            group = PlantGroup.objects.filter(
                user=user,
                name__iexact=group_name
            ).first()
        else:
            group = PlantGroup.objects.filter(
                user=user,
                name=group_name
            ).first()

        if group:
            self.groups_cache[search_name] = group
            return {
                'group': group,
                'created': False
            }

        # Gruppe erstellen
        if self.dry_run:
            self.stdout.write(self.style.WARNING(f'    🏷️  Würde Gruppe "{group_name}" erstellen'))
            return {
                'group': None,
                'created': True
            }

        group = PlantGroup.objects.create(
            name=group_name,
            user=user
        )

        self.groups_cache[search_name] = group
        self.stdout.write(self.style.SUCCESS(f'    🏷️  Gruppe "{group_name}" erstellt'))

        return {
            'group': group,
            'created': True
        }

    def _get_or_create_plant(self, plant_name, user, group=None):
        """Findet Pflanze oder erstellt sie (falls --create-missing)"""
        search_name = plant_name.lower() if self.case_insensitive else plant_name

        # Im Cache suchen
        if search_name in self.plants_cache:
            plant = self.plants_cache[search_name]

            # Gruppe aktualisieren falls nötig
            if group and plant.group != group and not self.dry_run:
                plant.group = group
                plant.save(update_fields=['group'])
                self.stdout.write(self.style.SUCCESS(
                    f'    ↻ Gruppe aktualisiert: {plant.name} → {group.name}'
                ))

            return {
                'plant': plant,
                'created': False
            }

        # In Datenbank suchen
        if self.case_insensitive:
            plant = Plant.objects.filter(
                user=user,
                name__iexact=plant_name
            ).first()
        else:
            plant = Plant.objects.filter(
                user=user,
                name=plant_name
            ).first()

        if plant:
            # Gruppe aktualisieren falls nötig
            if group and plant.group != group and not self.dry_run:
                plant.group = group
                plant.save(update_fields=['group'])
                self.stdout.write(self.style.SUCCESS(
                    f'    ↻ Gruppe aktualisiert: {plant.name} → {group.name}'
                ))

            self.plants_cache[search_name] = plant
            return {
                'plant': plant,
                'created': False
            }

        # Pflanze nicht gefunden
        if not self.create_missing:
            return {
                'plant': None,
                'created': False
            }

        # Pflanze erstellen
        if self.dry_run:
            self.stdout.write(self.style.WARNING(f'    ℹ️  Würde Pflanze "{plant_name}" erstellen'))
            return {
                'plant': None,
                'created': True
            }

        # Behalte Original-Schreibweise mit Unterstrichen
        plant = Plant.objects.create(
            name=plant_name,
            user=user,
            group=group
        )

        self.plants_cache[search_name] = plant

        group_info = f" in {group.name}" if group else ""
        self.stdout.write(self.style.SUCCESS(f'    🆕 Pflanze "{plant_name}"{group_info} erstellt'))

        return {
            'plant': plant,
            'created': True
        }