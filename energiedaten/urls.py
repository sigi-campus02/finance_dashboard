from django.urls import path
from energiedaten import views

app_name = 'energiedaten'

urlpatterns = [
    path('', views.energiedaten_dashboard, name='dashboard'),
    path('detail/', views.energiedaten_detail, name='detail'),
]