from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Haupt-Seiten
    path('', views.dashboard, name='dashboard'),
    path('transactions/', views.transactions_list, name='transactions'),
    path('transactions/household/', views.household_transactions, name='household_transactions'),
    path('transactions/add/', views.add_transaction, name='add_transaction'),
    path('transactions/delete/<int:pk>/', views.delete_transaction, name='delete_transaction'),  # NEU
    path('transactions/undo/', views.undo_delete, name='undo_delete'),  # NEU
    path('assets/', views.asset_overview, name='asset_overview'),

    # API Endpoints für Charts
    path('api/monthly-spending/', views.api_monthly_spending, name='api_monthly_spending'),
    path('api/category-breakdown/', views.api_category_breakdown, name='api_category_breakdown'),
    path('api/top-payees/', views.api_top_payees, name='api_top_payees'),
]