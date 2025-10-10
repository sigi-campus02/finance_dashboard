from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Haupt-Seiten
    path('', views.dashboard, name='dashboard'),
    path('transactions/', views.transactions_list, name='transactions'),
    path('transactions/household/', views.household_transactions, name='household_transactions'),
    path('transactions/add/', views.add_transaction, name='add_transaction'),
    path('transactions/delete/<int:pk>/', views.delete_transaction, name='delete_transaction'),
    path('transactions/undo/', views.undo_delete, name='undo_delete'),
    path('assets/', views.asset_overview, name='asset_overview'),

    # Scheduled Transactions
    path('scheduled/', views.scheduled_transactions_list, name='scheduled_transactions'),
    path('scheduled/add/', views.scheduled_transaction_create, name='scheduled_transaction_create'),
    path('scheduled/edit/<int:pk>/', views.scheduled_transaction_edit, name='scheduled_transaction_edit'),
    path('scheduled/toggle/<int:pk>/', views.scheduled_transaction_toggle, name='scheduled_transaction_toggle'),
    path('scheduled/delete/<int:pk>/', views.scheduled_transaction_delete, name='scheduled_transaction_delete'),
    path('scheduled/execute/<int:pk>/', views.scheduled_transaction_execute_now, name='scheduled_transaction_execute'),

    # API Endpoints für Charts
    path('api/monthly-spending/', views.api_monthly_spending, name='api_monthly_spending'),
    path('api/category-breakdown/', views.api_category_breakdown, name='api_category_breakdown'),
    path('api/top-payees/', views.api_top_payees, name='api_top_payees'),

    # API Endpoints für Formular
    path('api/payee-suggestions/', views.api_get_payee_suggestions, name='api_payee_suggestions'),
]