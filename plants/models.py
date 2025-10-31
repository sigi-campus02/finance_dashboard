# plants/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings


def get_plant_storage():
    """
    Liefert den Storage für Plant-Fotos (R2, falls aktiviert).
    Bei fehlender Konfiguration: None => Django FileSystemStorage.
    """
    if not settings.configured or not getattr(settings, "USE_R2_STORAGE", False):
        return None

    from .storage import PlantPhotoStorage  # Lazy import
    try:
        return PlantPhotoStorage()
    except ValueError:
        # Fallback auf Default-Storage (lokal), wenn Credentials fehlen
        return None


def plant_image_upload_to(instance, filename: str) -> str:
    """
    Generiert den Pfad anhand des Aufnahmedatums (captured_at).
    Fällt auf Jetztzeit zurück, falls fehlt.
    Endgültiger Key in R2: <storage.location>/plants/YYYY/MM/filename
    (storage.location kommt aus PlantPhotoStorage)
    """
    dt = getattr(instance, "captured_at", None) or timezone.now()
    return f"plants/{dt:%Y/%m}/{filename}"

class PlantRoom(models.Model):
    """
    Räume/Standorte für Pflanzen (z. B. Wohnzimmer, Balkon, Schlafzimmer …)
    Pro User eindeutig nach Name.
    """
    name = models.CharField(max_length=100, verbose_name="Raum")
    is_outdoor = models.BooleanField(default=False, verbose_name="Außenbereich")
    icon = models.CharField(max_length=50, blank=True, verbose_name="Icon (Bootstrap-Icon-Key, optional)")
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ["name"]
        verbose_name = "Pflanzenraum"
        verbose_name_plural = "Pflanzenräume"
        unique_together = ["name", "user"]

    def __str__(self):
        return self.name


class PlantGroup(models.Model):
    # (unverändert)
    name = models.CharField(max_length=200, verbose_name="Gruppenname")
    description = models.TextField(blank=True, verbose_name="Beschreibung")
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ["name"]
        verbose_name = "Pflanzengruppe"
        verbose_name_plural = "Pflanzengruppen"
        unique_together = ["name", "user"]

    def __str__(self):
        return self.name

    def plant_count(self):
        return self.plants.count()

class Plant(models.Model):
    name = models.CharField(max_length=200, verbose_name="Pflanzenname")
    species = models.CharField(max_length=200, blank=True, verbose_name="Art/Sorte")
    group = models.ForeignKey(
        PlantGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plants",
        verbose_name="Gruppe",
    )
    # NEU: Räume
    rooms = models.ManyToManyField(
        PlantRoom,
        blank=True,
        related_name="plants",
        verbose_name="Räume/Standorte"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        ordering = ["group__name", "name"]
        verbose_name = "Pflanze"
        verbose_name_plural = "Pflanzen"

    def __str__(self):
        return f"{self.group.name} → {self.name}" if self.group else self.name

    def latest_image(self):
        return self.images.first()

    def image_count(self):
        return self.images.count()


class PlantImage(models.Model):
    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to=plant_image_upload_to,
        storage=get_plant_storage(),
    )
    captured_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Aufnahmedatum")
    notes = models.TextField(blank=True, verbose_name="Notizen")

    class Meta:
        ordering = ["-captured_at"]
        verbose_name = "Pflanzenbild"
        verbose_name_plural = "Pflanzenbilder"

    def __str__(self):
        ts = (self.captured_at or timezone.now()).strftime("%d.%m.%Y %H:%M")
        return f"{self.plant.name} - {ts}"