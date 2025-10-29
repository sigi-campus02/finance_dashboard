from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings
import os


class PlantPhotoStorage(S3Boto3Storage):
    """Cloudflare R2 Storage für Pflanzenfotos"""

    # Bucket aus Settings oder fallback
    bucket_name = getattr(settings, 'PLANT_PHOTOS_BUCKET_NAME', 'plant-photos')

    # R2 Credentials
    access_key = settings.AWS_ACCESS_KEY_ID
    secret_key = settings.AWS_SECRET_ACCESS_KEY
    endpoint_url = settings.AWS_S3_ENDPOINT_URL

    # R2 Settings
    region_name = 'auto'
    signature_version = 's3v4'
    default_acl = None
    file_overwrite = False
    querystring_auth = True
    max_memory_size = 100 * 1024 * 1024  # 100 MB

    def __init__(self, **settings_dict):
        super().__init__(**settings_dict)

        # Public URL nutzen falls gesetzt
        public_url = getattr(settings, 'PLANT_PHOTOS_PUBLIC_URL', '')
        if public_url:
            self.custom_domain = public_url.replace('https://', '').replace('http://', '')
            self.url_protocol = 'https:'