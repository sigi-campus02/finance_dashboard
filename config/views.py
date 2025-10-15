from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils.cache import patch_cache_control


def _serve_pwa_static(filename: str, content_type: str) -> FileResponse:
    file_path = Path(settings.BASE_DIR) / 'static' / filename
    if not file_path.exists():
        raise Http404("Datei nicht gefunden")

    response = FileResponse(file_path.open('rb'), content_type=content_type)
    patch_cache_control(
        response,
        max_age=0,
        no_cache=True,
        no_store=True,
        must_revalidate=True,
    )
    return response


def service_worker(request):
    """Service Worker mit kurzen Cache-Headern ausliefern."""
    response = _serve_pwa_static('service-worker.js', 'application/javascript')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Service-Worker-Allowed'] = '/'
    return response


def manifest(request):
    """PWA Manifest mit passenden Headern ausliefern."""
    response = _serve_pwa_static('manifest.json', 'application/manifest+json')
    response['X-Content-Type-Options'] = 'nosniff'
    return response
