from django.urls import path
from .views import (
    bitpanda_dashboard,
    bitpanda_sync,
    api_bitpanda_portfolio_chart,
)
app_name = 'bitpanda'

urlpatterns = [
    # Bitpanda Integration
    path('', bitpanda_dashboard, name='bitpanda_dashboard'),
    path('bitpanda/sync/', bitpanda_sync, name='bitpanda_sync'),

    # API Endpoints für Bitpanda
    path('api/bitpanda/portfolio-chart/', api_bitpanda_portfolio_chart, name='api_bitpanda_portfolio_chart'),
]