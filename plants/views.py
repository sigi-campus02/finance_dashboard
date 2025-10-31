from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Plant, PlantImage, PlantGroup, PlantRoom
from django.core.files.base import ContentFile
from django.db.models import Count, Max
from PIL import Image, ExifTags
import base64, os, re
from datetime import datetime

@login_required
def plant_group_list(request):
    """
    Übersicht aller Pflanzengruppen mit:
    - Anzahl Pflanzen
    - Anzahl Fotos (gesamt)
    - Letztes Foto-Datum
    - Cover-Bild (letztes Bild aus der Gruppe, wenn vorhanden)
    """
    groups = (
        PlantGroup.objects
        .annotate(
            plant_count=Count("plants", distinct=True),
            photo_count=Count("plants__images", distinct=True),
            last_photo_at=Max("plants__images__captured_at"),
        )
        .order_by("name")
    )

    # Cover-Bilder minimalinvasiv bestimmen (vermeidet komplexe Subqueries):
    # hole für Gruppen mit Fotos jeweils 1 jüngstes Bild
    cover_map = {}
    cover_qs = (
        PlantImage.objects
        .select_related("plant", "plant__group")
        .order_by("plant__group_id", "-captured_at")
    )
    for img in cover_qs:
        gid = img.plant.group_id
        if gid and gid not in cover_map:
            cover_map[gid] = img
    # mappen
    groups_with_cover = [
        (g, cover_map.get(g.id)) for g in groups
    ]

    return render(request, "plants/plant_group_list.html", {
        "groups_with_cover": groups_with_cover,
    })



@login_required
def plant_list(request, group_id=None):
    groups = PlantGroup.objects.filter(user=request.user).order_by("name")
    rooms_all = PlantRoom.objects.filter(user=request.user).order_by("name")

    selected_group = request.GET.get("group") or (str(group_id) if group_id else "")
    selected_plant = request.GET.get("plant") or ""
    selected_room  = request.GET.get("room") or ""

    qs = (
        Plant.objects
        .filter(user=request.user)
        .prefetch_related("images", "group", "rooms")
        .order_by("group__name", "name")
    )

    current_group = None
    if selected_group:
        qs = qs.filter(group_id=selected_group)
        current_group = groups.filter(id=selected_group).first()

    if selected_room:
        qs = qs.filter(rooms__id=selected_room)

    if selected_plant:
        qs = qs.filter(id=selected_plant)

    plants = list(qs.distinct())
    total_images = sum(p.images.count() for p in plants)

    # Plant-Options (wie zuvor)
    if selected_group:
        plant_options = Plant.objects.filter(user=request.user, group_id=selected_group).order_by("name")
    else:
        plant_options = Plant.objects.filter(user=request.user).order_by("group__name", "name")

    return render(request, "plants/plant_list.html", {
        "plants": plants,
        "total_images": total_images,
        "current_group": current_group,
        "groups": groups,
        "plant_options": plant_options,
        "rooms_all": rooms_all,
        "selected_group": selected_group,
        "selected_plant": selected_plant,
        "selected_room": selected_room,
    })


@login_required
def plant_timeline(request, plant_id):
    """Timeline für einzelne Pflanze"""
    plant = get_object_or_404(Plant, id=plant_id)
    images = plant.images.all()  # Bereits sortiert durch Meta ordering
    return render(request, 'plants/plant_timeline.html', {
        'plant': plant,
        'images': images
    })


_SAFE_NAME_RE = re.compile(r'[^A-Za-z0-9_]+')

def normalize_plant_name(name: str) -> str:
    """
    Erlaubt nur A-Z a-z 0-9 und Unterstrich. Entfernt Spaces/Sonderzeichen.
    Beispiel: "Basilikum Chianti (großer Ton)" -> "BasilikumChianti_großerTon" -> "BasilikumChianti_großerTon"
    (Umlaute/Sonderzeichen werden entfernt, wenn sie nicht im Set liegen.)
    """
    # Option: einfache Transliteration könnte ergänzt werden (ä->ae etc.)
    cleaned = name.replace(" ", "_")
    cleaned = _SAFE_NAME_RE.sub("", cleaned)
    # Doppel-Underscores auf einen reduzieren
    cleaned = re.sub(r'_{2,}', '_', cleaned).strip('_')
    return cleaned or "Plant"

def exif_datetime(file_obj) -> datetime | None:
    """
    Versucht EXIF DateTimeOriginal/DateTime zu lesen und nach UTC-naivem datetime zu parsen.
    Gibt None zurück, wenn nicht vorhanden/lesbar.
    """
    try:
        # Datei in Bytes laden (Position sichern/zurücksetzen)
        pos = file_obj.tell() if hasattr(file_obj, "tell") else None
        file_obj.seek(0)
        im = Image.open(file_obj)
        exif = im.getexif()
        if not exif:
            if pos is not None: file_obj.seek(pos)
            return None

        # Mapping der EXIF-Schlüssel
        tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        dt_raw = tag_map.get("DateTimeOriginal") or tag_map.get("DateTime")
        if not dt_raw:
            if pos is not None: file_obj.seek(pos)
            return None

        # Formate: "YYYY:MM:DD HH:MM:SS"
        dt = datetime.strptime(str(dt_raw), "%Y:%m:%d %H:%M:%S")
        # wir machen es timezone-aware (lokale TZ), damit upload_to korrekt datiert
        return timezone.make_aware(dt, timezone.get_current_timezone())
    except Exception:
        return None
    finally:
        # Dateizeiger zurücksetzen, damit Django speichern kann
        try:
            if pos is not None:
                file_obj.seek(pos)
        except Exception:
            pass

def next_index_for_day(plant: Plant, day: datetime) -> int:
    """
    Ermittelt den nächsten laufenden Index (NN) für diesen Pflanzentag (YYYYMMDD).
    Start = 1, wenn noch kein Bild vorhanden. Zählt existierende Bilder dieses Tages.
    """
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    count = PlantImage.objects.filter(
        plant=plant,
        captured_at__gte=day_start,
        captured_at__lte=day_end,
    ).count()
    return count + 1

def build_filename(plant: Plant, captured_at: datetime, ext: str, index: int | None) -> str:
    """
    Baut 'PlantName_YYYYMMDD[_NN].ext'
    """
    base = normalize_plant_name(plant.name)
    date_part = captured_at.strftime("%Y%m%d")
    ext = (ext or "jpg").lower().lstrip(".")
    if index and index > 1:
        return f"{base}_{date_part}_{index:02d}.{ext}"
    return f"{base}_{date_part}.{ext}"


@login_required
def add_image(request, plant_id):
    """
    Bild hinzufügen:
    - Base64 (Kamera) -> now(), Name nach Konvention
    - Datei-Upload (Galerie) -> EXIF-Datum, sonst now()
    - captured_at wird gesetzt, damit upload_to den richtigen YYYY/MM-Pfad nutzt
    - Dateiname folgt 'PlantName_YYYYMMDD[_NN].ext'
    """
    plant = get_object_or_404(Plant, id=plant_id, user=request.user)

    if request.method != 'POST':
        # Bei GET zurück zur Timeline
        return redirect('plants:plant_timeline', plant_id=plant_id)

    notes = request.POST.get('notes', '').strip()

    # Fall 1: Base64 aus Kamera
    if 'image_data' in request.POST:
        try:
            image_data = request.POST['image_data']
            fmt, b64 = image_data.split(';base64,')
            # fmt z.B. "data:image/jpeg"
            ext = (fmt.split('/')[-1] or 'jpg').lower()
            captured_at = timezone.now()  # Kamera -> jetzt
            index = next_index_for_day(plant, captured_at)
            filename = build_filename(plant, captured_at, ext, index)

            raw = base64.b64decode(b64)
            content = ContentFile(raw, name=filename)

            PlantImage.objects.create(
                plant=plant,
                image=content,          # upload_to nutzt captured_at (siehe unten)
                captured_at=captured_at,
                notes=notes,
            )
        except Exception as e:
            return HttpResponseBadRequest(f"Kamera-Upload fehlgeschlagen: {e}")

        return redirect('plants:plant_timeline', plant_id=plant_id)

    # Fall 2: klassischer Datei-Upload (Galerie)
    if 'image' in request.FILES:
        up_file = request.FILES['image']

        # EXIF-Datum lesen (wenn möglich), sonst now()
        # Achtung: für EXIF muss ein PIL-lesbarer Stream vorliegen
        file_for_exif = up_file.file if hasattr(up_file, "file") else up_file
        captured_at = exif_datetime(file_for_exif) or timezone.now()

        # Erweiterung bestimmen
        _, orig_ext = os.path.splitext(up_file.name)
        ext = (orig_ext or ".jpg").lstrip('.').lower()

        # Index bestimmen und Zielfilename bauen
        index = next_index_for_day(plant, captured_at)
        filename = build_filename(plant, captured_at, ext, index)

        # WICHTIG: dem Upload das neue .name geben, damit S3/R2-Key stimmt
        up_file.name = filename

        PlantImage.objects.create(
            plant=plant,
            image=up_file,
            captured_at=captured_at,
            notes=notes,
        )
        return redirect('plants:plant_timeline', plant_id=plant_id)

    return HttpResponseBadRequest("Kein Bild gefunden.")


@login_required
def create_plant(request):
    """Neue Pflanze anlegen"""
    if request.method == 'POST':
        plant = Plant.objects.create(
            name=request.POST['name'],
            species=request.POST.get('species', ''),
            user=request.user
        )
        return redirect('plants:plant_timeline', plant_id=plant.id)
    return render(request, 'plants/create_plant.html')


# ========== NEUE VIEWS ==========

@login_required
def edit_plant(request, plant_id):
    """Pflanze bearbeiten"""
    plant = get_object_or_404(Plant, id=plant_id, user=request.user)

    if request.method == 'POST':
        plant.name = request.POST['name']
        plant.species = request.POST.get('species', '')
        plant.save()
        return redirect('plants:plant_list')

    return redirect('plants:plant_list')


@login_required
def delete_plant(request, plant_id):
    """Pflanze löschen"""
    plant = get_object_or_404(Plant, id=plant_id, user=request.user)

    if request.method == 'POST':
        plant.delete()  # Bilder werden durch CASCADE automatisch gelöscht
        return redirect('plants:plant_list')

    return redirect('plants:plant_list')