# plants/storage.py
import os
import mimetypes
from storages.backends.s3boto3 import S3Boto3Storage


class PlantPhotoStorage(S3Boto3Storage):
    """
    Cloudflare R2 Storage für Pflanzenfotos.
    - eigener Bucket (PLANT_PHOTOS_BUCKET_NAME)
    - Basis-Pfad (location) = 'plant_photos'
    - setzt ContentType automatisch
    """

    # Fester Teil der Konfiguration
    location = "plant_photos"         # Präfix im Bucket
    region_name = "auto"
    signature_version = "s3v4"
    default_acl = None
    file_overwrite = False
    querystring_auth = True
    max_memory_size = 100 * 1024 * 1024  # 100 MB

    def __init__(self, **kwargs):
        # Env-Variablen erst hier lesen (robuster gegen Import-Timing)
        self.access_key = os.environ.get("R2_ACCESS_KEY_ID")
        self.secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
        self.endpoint_url = os.environ.get("R2_ENDPOINT_URL")
        self.bucket_name = os.environ.get("PLANT_PHOTOS_BUCKET_NAME", "plant-photos")

        if not all([self.access_key, self.secret_key, self.endpoint_url]):
            raise ValueError(
                "R2 Credentials fehlen! Setze R2_ACCESS_KEY_ID, "
                "R2_SECRET_SECRET_KEY und R2_ENDPOINT_URL."
            )

        public_url = os.environ.get("PLANT_PHOTOS_PUBLIC_URL", "")
        if public_url:
            self.custom_domain = public_url.replace("https://", "").replace("http://", "")
            self.url_protocol = "https:"
            self.querystring_auth = False  # Unsigned URLs

        super().__init__(**kwargs)

    def get_object_parameters(self, name):
        """
        Zusätzliche PUT-Parameter: ContentType (und optional CacheControl).
        """
        params = super().get_object_parameters(name)
        params.setdefault("ContentType", mimetypes.guess_type(name)[0] or "application/octet-stream")
        # Optional: langfristiges Caching für statische Bilder
        params.setdefault("CacheControl", "public, max-age=31536000, immutable")
        return params
