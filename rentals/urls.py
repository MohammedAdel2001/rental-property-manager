from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('rent-roll/', views.rent_roll, name='rent_roll'),
    path('payments/export/', views.export_payments, name='export_payments'),
    path('<str:entity>/', views.record_list, name='record_list'),
    path('<str:entity>/add/', views.record_form, name='record_create'),
    path('<str:entity>/<int:pk>/', views.record_detail, name='record_detail'),
    path('<str:entity>/<int:pk>/edit/', views.record_form, name='record_edit'),
    path('<str:entity>/<int:pk>/delete/', views.record_delete, name='record_delete'),
]
