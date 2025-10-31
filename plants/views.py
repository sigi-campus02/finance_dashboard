from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Plant, PlantImage, PlantGroup
import base64
from django.core.files.base import ContentFile
from django.db.models import Count, Max


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
    # --- Stammdaten für Selects
    groups = PlantGroup.objects.order_by("name")

    # GET-Filter
    selected_group = request.GET.get("group") or (str(group_id) if group_id else "")
    selected_plant = request.GET.get("plant") or ""

    qs = (
        Plant.objects
        .prefetch_related("images", "group")
        .order_by("group__name", "name")
    )

    current_group = None
    if selected_group:
        qs = qs.filter(group_id=selected_group)
        try:
            current_group = groups.get(id=selected_group)
        except PlantGroup.DoesNotExist:
            current_group = None

    if selected_plant:
        qs = qs.filter(id=selected_plant)

    plants = list(qs)

    # Plant-Optionen im Select:
    # - wenn Gruppe gewählt: nur Pflanzen dieser Gruppe
    # - sonst alle
    if selected_group:
        plant_options = Plant.objects.filter(
            group_id=selected_group
        ).order_by("name")
    else:
        plant_options = Plant.objects.order_by("group__name", "name")

    total_images = sum(p.images.count() for p in plants)

    return render(request, "plants/plant_list.html", {
        "plants": plants,
        "total_images": total_images,
        "current_group": current_group,
        "groups": groups,
        "plant_options": plant_options,
        "selected_group": selected_group,
        "selected_plant": selected_plant,
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


@login_required
def add_image(request, plant_id):
    """Bild hinzufügen (auch via Camera API)"""
    plant = get_object_or_404(Plant, id=plant_id, user=request.user)

    if request.method == 'POST':
        # Handling für base64 Bild von Camera API
        if 'image_data' in request.POST:
            image_data = request.POST['image_data']
            format, imgstr = image_data.split(';base64,')
            ext = format.split('/')[-1]

            image_file = ContentFile(
                base64.b64decode(imgstr),
                name=f'plant_{plant_id}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.{ext}'
            )

            PlantImage.objects.create(
                plant=plant,
                image=image_file,
                notes=request.POST.get('notes', '')
            )

        # Handling für normalen File Upload
        elif 'image' in request.FILES:
            PlantImage.objects.create(
                plant=plant,
                image=request.FILES['image'],
                notes=request.POST.get('notes', '')
            )

        return redirect('plants:plant_timeline', plant_id=plant_id)

    # ← GEÄNDERT: Bei GET direkt zur Timeline mit open_camera Parameter
    return redirect('plants:plant_timeline', plant_id=plant_id)


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