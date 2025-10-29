from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone  # ← ERGÄNZT
from .models import Plant, PlantImage
import base64
from django.core.files.base import ContentFile


@login_required
def plant_list(request):
    """Übersicht aller Pflanzen mit Statistiken"""
    plants = Plant.objects.filter(user=request.user).prefetch_related('images')

    # ← ERGÄNZT: Gesamtanzahl Bilder berechnen
    total_images = sum(plant.images.count() for plant in plants)

    return render(request, 'plants/plant_list.html', {
        'plants': plants,
        'total_images': total_images  # ← ERGÄNZT
    })


@login_required
def plant_timeline(request, plant_id):
    """Timeline für einzelne Pflanze"""
    plant = get_object_or_404(Plant, id=plant_id, user=request.user)
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