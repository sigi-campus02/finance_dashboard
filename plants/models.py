from django.db import models
from django.contrib.auth.models import User
from django.conf import settings


def get_plant_storage():
    """Gibt Storage zurück - LAZY Import!"""
    if not settings.configured or not getattr(settings, 'USE_R2_STORAGE', False):
        return None  # FileSystemStorage

    # ← WICHTIG: Import erst HIER, nicht oben!
    from .storage import PlantPhotoStorage
    return PlantPhotoStorage()


class Plant(models.Model):
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
        return self.images.first()


class PlantImage(models.Model):
    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to='plants/%Y/%m/',
        storage=get_plant_storage()
    )
    captured_at = models.DateTimeField(auto_now_add=True, verbose_name="Aufnahmedatum")
    notes = models.TextField(blank=True, verbose_name="Notizen")

    class Meta:
        ordering = ['-captured_at']
        verbose_name = "Pflanzenbild"
        verbose_name_plural = "Pflanzenbilder"