from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
from django.utils.cache import patch_cache_control
from django.contrib.auth import views as auth_views
from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login
from finance.models import RegisteredDevice
import hashlib
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)


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


class CustomLoginView(auth_views.LoginView):
    """Erweiterte Login-View mit Geräteregistrierung"""
    template_name = 'login.html'

    def form_valid(self, form):
        """Wird nach erfolgreicher Anmeldung aufgerufen"""
        user = form.get_user()

        # Gerät identifizieren
        device_fingerprint = self.generate_device_fingerprint()

        try:
            # Prüfen ob Gerät bereits registriert ist
            device, created = RegisteredDevice.objects.get_or_create(
                user=user,
                device_fingerprint=device_fingerprint,
                defaults={'device_name': self.get_default_device_name()}
            )

        except IntegrityError as e:
            # Falls es einen Race-Condition gibt, hole das existierende Device
            logger.warning(f"IntegrityError beim Device-Login für {user.username}: {e}")
            try:
                device = RegisteredDevice.objects.get(
                    user=user,
                    device_fingerprint=device_fingerprint
                )
                created = False
            except RegisteredDevice.DoesNotExist:
                # Sollte nicht passieren, aber zur Sicherheit
                return render(self.request, 'device_error.html', {
                    'error': 'Fehler bei der Geräteregistrierung. Bitte kontaktiere den Administrator.'
                })

        # Wenn Gerät deaktiviert ist, Login ablehnen
        if not device.is_active:
            return render(self.request, 'device_not_authorized.html', {
                'device': device,
                'user': user
            })

        # Bei neuem Gerät: Log (später Email-Benachrichtigung möglich)
        if created:
            logger.info(f"Neues Gerät registriert für {user.username}: {device.device_name}")

        # Token in Session speichern
        self.request.session['device_token'] = str(device.device_token)

        # Normaler Login
        auth_login(self.request, user)

        return redirect(self.get_success_url())

    def generate_device_fingerprint(self):
        """Erstellt einen eindeutigen Fingerprint für das Gerät"""
        user_agent = self.request.META.get('HTTP_USER_AGENT', '')
        accept_language = self.request.META.get('HTTP_ACCEPT_LANGUAGE', '')

        # Kombiniere mehrere Browser-Infos für eindeutigen Fingerprint
        fingerprint_string = f"{user_agent}:{accept_language}"
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()

    def get_default_device_name(self):
        """Versucht automatisch einen Namen für das Gerät zu generieren"""
        user_agent = self.request.META.get('HTTP_USER_AGENT', '').lower()

        # Einfache Device-Erkennung
        if 'mobile' in user_agent or 'android' in user_agent:
            return 'Handy (Android)'
        elif 'iphone' in user_agent or 'ipad' in user_agent:
            return 'iPhone/iPad'
        elif 'windows' in user_agent:
            return 'PC (Windows)'
        elif 'mac' in user_agent:
            return 'Mac'
        elif 'linux' in user_agent:
            return 'PC (Linux)'
        else:
            return 'Neues Gerät'