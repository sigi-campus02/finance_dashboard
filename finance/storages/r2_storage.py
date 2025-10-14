# finance/storages/r2_storage.py
# Erstelle: finance/storages/__init__.py (leer)

from storages.backends.s3boto3 import S3Boto3Storage
import os


class CloudflareR2Storage(S3Boto3Storage):
    """
    Dedizierte Storage-Klasse für Cloudflare R2.
    Nur für Billa-PDFs, nicht für andere Files.
    """

    access_key = os.environ.get('R2_ACCESS_KEY_ID')
    secret_key = os.environ.get('R2_SECRET_ACCESS_KEY')
    bucket_name = os.environ.get('R2_BUCKET_NAME', 'billa-rechnungen')
    endpoint_url = os.environ.get('R2_ENDPOINT_URL')
    region_name = 'auto'
    signature_version = 's3v4'

    # Security
    default_acl = None
    file_overwrite = False
    querystring_auth = True

    # Performance
    max_memory_size = 100 * 1024 * 1024  # 100 MB

    # Ordner-Struktur in R2
    location = 'billa_pdfs'  # Alle PDFs in /billa_pdfs/

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Prüfe ob Credentials gesetzt sind
        if not all([self.access_key, self.secret_key, self.endpoint_url]):
            raise ValueError(
                "R2 Credentials fehlen! Setze R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY und R2_ENDPOINT_URL in Environment Variables."
            )