from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views
from .views import CustomLoginView
from finance import views as finance_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', finance_views.custom_logout, name='logout'),

    # Service Worker und Manifest mit kurzen Cache-Headern ausliefern
    path('service-worker.js', views.service_worker, name='service-worker'),
    path('manifest.json', views.manifest, name='manifest'),

    path('', include('finance.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)