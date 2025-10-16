# finance/middleware.py
from django.shortcuts import redirect, render
from django.urls import reverse
from finance.models import RegisteredDevice
from django.utils.deprecation import MiddlewareMixin


class DeviceAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware zur Überprüfung ob das angemeldete Gerät autorisiert ist.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def process_request(self, request):
        # Nur für authentifizierte User prüfen
        if not request.user.is_authenticated:
            return None

        # Öffentliche URLs
        public_paths = self._get_public_paths(request)
        if request.path in public_paths:
            return None

        # **VERBESSERT: Prüfe persistent Cookie statt Session**
        device_token = request.COOKIES.get('device_id') or request.session.get('device_token')

        if not device_token:
            # Kein Token → Logout und redirect
            from django.contrib.auth import logout
            logout(request)
            return redirect('login')

        # Prüfe ob Device existiert und aktiv ist
        try:
            device = RegisteredDevice.objects.select_related('user').get(
                device_token=device_token,
                user=request.user,
                is_active=True
            )
            # Update last_used
            RegisteredDevice.objects.filter(pk=device.pk).update(last_used=device.last_used)

        except RegisteredDevice.DoesNotExist:
            # Device nicht gefunden oder deaktiviert
            from django.contrib.auth import logout
            logout(request)

            # **WICHTIG: Lösche ungültigen Cookie**
            response = render(request, 'device_not_authorized.html', {
                'show_reactivation_hint': True
            })
            response.delete_cookie('device_id')
            return response

        return None

    def _get_public_paths(self, request):
        """Gibt alle öffentlichen Pfade zurück"""
        public_paths = [
            reverse('login'),
            reverse('logout'),
            '/admin/login/',
        ]

        try:
            public_paths.extend([
                reverse('service-worker'),
                reverse('manifest'),
            ])
        except:
            pass

        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            public_paths.append(request.path)

        return public_paths


class DeviceTrackingMiddleware(MiddlewareMixin):
    """
    Optionale Middleware: Tracked Device-Aktivität für Sicherheits-Logging.
    Kann zusätzlich zur DeviceAuthenticationMiddleware verwendet werden.
    """

    def process_request(self, request):
        if request.user.is_authenticated:
            device_token = request.session.get('device_token')
            if device_token:
                # Speichere letzten Request-Path im Session (für Debugging)
                request.session['last_path'] = request.path
                request.session['last_activity'] = str(request.META.get('HTTP_USER_AGENT', ''))

        return None