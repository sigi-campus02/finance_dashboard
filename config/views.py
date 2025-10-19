from django.contrib.auth import views as auth_views
from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login
from django.db import IntegrityError
from finance.models import RegisteredDevice
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
import hashlib
import logging
import uuid

logger = logging.getLogger(__name__)


class CustomLoginView(auth_views.LoginView):
    """Erweiterte Login-View mit Cookie-basierter Geräteregistrierung"""
    template_name = 'login.html'

    def form_valid(self, form):
        """Wird nach erfolgreicher Anmeldung aufgerufen"""
        user = form.get_user()

        # Prüfe ob bereits ein persistent device token im Cookie existiert
        persistent_token = self.request.COOKIES.get('device_id')
        device = None
        created = False

        # Strategie 1: Cookie vorhanden → Suche Device per Token
        if persistent_token:
            try:
                device = RegisteredDevice.objects.get(
                    device_token=persistent_token,
                    user=user
                )

                # Prüfe ob Gerät noch aktiv ist
                if not device.is_active:
                    device.is_active = True
                    device.save(update_fields=['is_active'])
                    logger.info(
                        "Reaktiviertes Gerät %s (%s) für Benutzer %s nach Cookie-Authentifizierung",
                        device.device_name,
                        device.device_token,
                        user.username,
                    )

            except RegisteredDevice.DoesNotExist:
                # Cookie existiert, aber Device nicht in DB → Wurde gelöscht
                device = None

        # Strategie 2: Kein Cookie ODER Device wurde gelöscht → Suche per Fingerprint
        if device is None:
            device_fingerprint = self.generate_device_fingerprint()

            try:
                # Versuche vorhandenes Device mit diesem Fingerprint zu finden
                device = RegisteredDevice.objects.get(
                    user=user,
                    device_fingerprint=device_fingerprint
                )

                # Prüfe Aktivstatus
                if not device.is_active:
                    device.is_active = True
                    device.save(update_fields=['is_active'])
                    logger.info(
                        "Reaktiviertes Gerät %s (%s) für Benutzer %s nach Fingerprint-Abgleich",
                        device.device_name,
                        device.device_token,
                        user.username,
                    )

                # Device gefunden → Verwende dessen Token
                persistent_token = str(device.device_token)
                logger.info(f"Bestehendes Device wiederverwendet für {user.username}")

            except RegisteredDevice.DoesNotExist:
                # Wirklich neues Device → Erstelle es
                try:
                    device = self.create_new_device(user, device_fingerprint)
                    persistent_token = str(device.device_token)
                    created = True
                    logger.info(f"Neues Gerät registriert für {user.username}: {device.device_name}")

                except IntegrityError as e:
                    # Race Condition oder anderer Fehler
                    logger.error(f"IntegrityError beim Device-Erstellen für {user.username}: {e}")
                    # Versuche nochmal zu finden
                    try:
                        device = RegisteredDevice.objects.get(
                            user=user,
                            device_fingerprint=device_fingerprint
                        )
                        if not device.is_active:
                            device.is_active = True
                            device.save(update_fields=['is_active'])
                            logger.info(
                                "Reaktiviertes Gerät %s (%s) für Benutzer %s nach IntegrityError",
                                device.device_name,
                                device.device_token,
                                user.username,
                            )
                        persistent_token = str(device.device_token)
                    except RegisteredDevice.DoesNotExist:
                        return render(self.request, 'device_error.html', {
                            'error': 'Fehler bei der Geräteregistrierung. Bitte kontaktiere den Administrator.'
                        })

        # Token in Session speichern (Backup)
        self.request.session['device_token'] = persistent_token

        # Normaler Login
        auth_login(self.request, user)

        # Setze persistent Cookie (1 Jahr Gültigkeit)
        response = redirect(self.get_success_url())
        response.set_cookie(
            'device_id',
            persistent_token,
            max_age=365 * 24 * 60 * 60,  # 1 Jahr
            httponly=True,  # JavaScript kann nicht darauf zugreifen
            secure=False,  # True in Production mit HTTPS!
            samesite='Lax'
        )

        return response

    def create_new_device(self, user, device_fingerprint):
        """Erstellt ein neues Gerät mit eindeutigem Token"""
        device_name = self.get_default_device_name()

        # Erstelle Device
        device = RegisteredDevice.objects.create(
            user=user,
            device_name=device_name,
            device_token=uuid.uuid4(),
            device_fingerprint=device_fingerprint
        )

        return device

    def generate_device_fingerprint(self):
        """
        Erstellt einen Fingerprint (als Backup für Cookie-Verlust)
        """
        user_agent = self.request.META.get('HTTP_USER_AGENT', '')
        accept_language = self.request.META.get('HTTP_ACCEPT_LANGUAGE', '')

        fingerprint_string = f"{user_agent}:{accept_language}"
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()

    def get_default_device_name(self):
        """Versucht automatisch einen Namen für das Gerät zu generieren"""
        user_agent = self.request.META.get('HTTP_USER_AGENT', '').lower()

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


# Service Worker View
@require_http_methods(["GET"])
def service_worker(request):
    """Serve service worker with correct content type"""
    try:
        with open('static/service-worker.js', 'r') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/javascript')
    except FileNotFoundError:
        return HttpResponse('// Service worker not found', content_type='application/javascript')


@require_http_methods(["GET"])
def manifest(request):
    """Serve manifest.json"""
    try:
        with open('static/manifest.json', 'r') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/json')
    except FileNotFoundError:
        return HttpResponse('{}', content_type='application/json')