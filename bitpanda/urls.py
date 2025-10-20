# bitpanda/urls.py
from django.urls import path
from . import views

app_name = 'bitpanda'

urlpatterns = [
    # Dashboard
    path('', views.bitpanda_dashboard, name='bitpanda_dashboard'),
    path('update-prices/', views.update_prices, name='update_prices'),
    path('api/portfolio-chart/', views.api_bitpanda_portfolio_chart, name='api_bitpanda_portfolio_chart'),
    path('api/asset-allocation/', views.api_bitpanda_asset_allocation, name='api_bitpanda_asset_allocation'),
]