from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Haupt-Seiten
    path('', views.home, name='home'),

    # Geräteverwaltung
    path('devices/', views.manage_devices, name='manage_devices'),
    path('devices/delete/<int:device_id>/', views.delete_device, name='delete_device'),

    path('dashboard/', views.dashboard, name='dashboard'),

    path('transactions/', views.transactions_list, name='transactions'),
    path('transactions/household/', views.household_transactions, name='household_transactions'),
    path('transactions/add/', views.add_transaction, name='add_transaction'),
    path('transactions/delete/<int:pk>/', views.delete_transaction, name='delete_transaction'),
    path('transactions/undo/', views.undo_delete, name='undo_delete'),
    path('transactions/update-date/<int:pk>/', views.update_transaction_date, name='update_transaction_date'),
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
    path('api/monthly-spending-drilldown/', views.api_monthly_spending_drilldown, name='api_monthly_spending_drilldown'),
    path('api/category-breakdown/', views.api_category_breakdown, name='api_category_breakdown'),
    path('api/top-payees/', views.api_top_payees, name='api_top_payees'),
    path('api/spending-trend/', views.api_spending_trend, name='api_spending_trend'),

    # API Endpoints für Formular
    path('api/payee-suggestions/', views.api_get_payee_suggestions, name='api_payee_suggestions'),

    # API Endpoint für Cron-Job
    path('api/cron/process-scheduled/', views.process_scheduled_transactions, name='process_scheduled'),

    # Receipt Scanner
    path('receipt-upload/', views.analyze_receipt_page, name='receipt_upload'),
    path('api/analyze-receipt/', views.analyze_receipt_image, name='api_analyze_receipt'),

    # Inline Transaction Creation
    path('api/transactions/create/', views.create_transaction_inline, name='create_transaction_inline'),

    # Investment Management
    path('investments/adjust/', views.adjust_investments, name='adjust_investments'),

    # API Endpoints für Investment Management
    path('api/asset-history/', views.api_asset_history, name='api_asset_history'),
    path('api/asset-category-details/', views.api_asset_category_details, name='api_asset_category_details'),
    path('api/income-payees/', views.api_income_payees, name='api_income_payees'),

    # Dashboard Haushalt
    path('dashboard/household/', views.household_dashboard, name='household_dashboard'),

    # API Endpoints für Haushalt-Dashboard
    path('api/household-monthly-spending/', views.api_household_monthly_spending, name='api_household_monthly_spending'),
    path('api/household-category-breakdown/', views.api_household_category_breakdown, name='api_household_category_breakdown'),

    # API Endpoints für CategoryGroup-Diagramme im Haushalt-Dashboard
    path('api/categorygroup-monthly-trend/', views.api_categorygroup_monthly_trend, name='api_categorygroup_monthly_trend'),
    path('api/categorygroup-year-comparison/', views.api_categorygroup_year_comparison, name='api_categorygroup_year_comparison'),
    path('api/categorygroup-quarterly-breakdown/', views.api_categorygroup_quarterly_breakdown, name='api_categorygroup_quarterly_breakdown'),
    path('api/categorygroup-stats/', views.api_categorygroup_stats, name='api_categorygroup_stats'),

    # API Endpoints für Supermarkt-Bereich (Kategorie id=5)
    path('api/supermarket-monthly-trend/', views.api_supermarket_monthly_trend, name='api_supermarket_monthly_trend'),
    path('api/supermarket-year-comparison/', views.api_supermarket_year_comparison, name='api_supermarket_year_comparison'),
    path('api/supermarket-stats/', views.api_supermarket_stats, name='api_supermarket_stats'),
    path('api/billa-combined-chart/', views.api_billa_combined_chart, name='api_billa_combined_chart'),

    # DEBUG Endpoints für Supermarkt-Details
    path('api/supermarket-transactions-detail/', views.api_supermarket_transactions_detail, name='api_supermarket_transactions_detail'),
    path('api/billa-transactions-detail/', views.api_billa_transactions_detail, name='api_billa_transactions_detail'),



]