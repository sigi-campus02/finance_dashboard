from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

# Storage Import
def get_plant_storage():
    """Gibt R2 Storage zurück wenn aktiviert, sonst FileSystem"""
    if settings.USE_R2_STORAGE:
        from .storage import PlantPhotoStorage
        return PlantPhotoStorage()
    return None  # Default FileSystemStorage


class Plant(models.Model):
    """Pflanze (z.B. Avokado, Monstera, etc.)"""
    name = models.CharField(max_length=200, verbose_name="Pflanzenname")
    species = models.CharField(max_length=200, blank=True, verbose_name="Art/Sorte")
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ['name']
        verbose_name = "Pflanze"
        verbose_name_plural = "Pflanzen"

    def __str__(self):
        return self.name

    def latest_image(self):
        """Neuestes Bild für Thumbnail"""
        return self.images.first()


class PlantImage(models.Model):
    """Foto einer Pflanze"""
    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to='plants/%Y/%m/',
        storage=get_plant_storage()  # ← Nutzt R2 wenn aktiviert
    )
    captured_at = models.DateTimeField(auto_now_add=True, verbose_name="Aufnahmedatum")
    notes = models.TextField(blank=True, verbose_name="Notizen")

    class Meta:
        ordering = ['-captured_at']
        verbose_name = "Pflanzenbild"
        verbose_name_plural = "Pflanzenbilder"

    def __str__(self):
        return f"{self.plant.name} - {self.captured_at.strftime('%d.%m.%Y %H:%M')}"