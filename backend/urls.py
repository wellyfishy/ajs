from django.urls import path
from . import views
from backend import views_dokumen

urlpatterns = [
    # Landing
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('teams/', views.teams, name='teams'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('panel/', views.dashboard, name='dashboard'),

    # Team
    path('panel/team/', views.team_list, name='team_list'),
    path('panel/team/tambah/', views.team_create, name='team_create'),
    path('panel/team/<int:pk>/edit/', views.team_edit, name='team_edit'),
    path('panel/team/<int:pk>/hapus/', views.team_delete, name='team_delete'),

    # Todo
    path('panel/todo/', views.todo_list, name='todo_list'),
    path('panel/todo/tambah/', views.todo_create, name='todo_create'),
    path('panel/todo/<int:pk>/edit/', views.todo_edit, name='todo_edit'),
    path('panel/todo/<int:pk>/hapus/', views.todo_delete, name='todo_delete'),
    path('panel/todo/<int:pk>/status/', views.todo_status, name='todo_status'),

    # Client
    path('panel/client/', views.client_list, name='client_list'),
    path('panel/client/tambah/', views.client_create, name='client_create'),
    path('panel/client/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('panel/client/<int:pk>/hapus/', views.client_delete, name='client_delete'),

    # Layanan
    path('panel/layanan/', views.layanan_list, name='layanan_list'),
    path('panel/layanan/tambah/', views.layanan_create, name='layanan_create'),
    path('panel/layanan/<int:pk>/edit/', views.layanan_edit, name='layanan_edit'),
    path('panel/layanan/<int:pk>/hapus/', views.layanan_delete, name='layanan_delete'),

    # Shipment
    path('panel/shipment/', views.shipment_list, name='shipment_list'),
    path('panel/shipment/tambah/', views.shipment_create, name='shipment_create'),
    path('panel/shipment/<int:pk>/edit/', views.shipment_edit, name='shipment_edit'),
    path('panel/shipment/<int:pk>/hapus/', views.shipment_delete, name='shipment_delete'),
    path('panel/shipment/<int:pk>/status/', views.shipment_status, name='shipment_status'),

    # Absensi
    path('panel/absensi/', views.absensi_list, name='absensi_list'),
    path('panel/absensi/masuk/', views.absen_masuk, name='absen_masuk'),
    path('panel/absensi/keluar/', views.absen_keluar, name='absen_keluar'),

    # Dokumen
    path('panel/dokumen/', views.dokumen_list, name='dokumen_list'),

    # User Management
    path('panel/user/', views.user_list, name='user_list'),
    path('panel/user/tambah/', views.user_create, name='user_create'),
    path('panel/user/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('panel/user/<int:pk>/hapus/', views.user_delete, name='user_delete'),

    # History
    path('panel/history/', views.history_list, name='history_list'),

    # Dokumen page
    path('dokumen/', views_dokumen.dokumen_page, name='dokumen_page'),

    # Dokumen APIs
    path('api/dokumen/',
         views_dokumen.api_list_dokumen,
         name='api_list_dokumen'),

    path('api/dokumen/upload/',
         views_dokumen.api_upload_dokumen,
         name='api_upload_dokumen'),

    path('api/dokumen/<int:dokumen_id>/progress/',
         views_dokumen.api_dokumen_progress,
         name='api_dokumen_progress'),

    path('api/dokumen/<int:dokumen_id>/delete/',
         views_dokumen.api_delete_dokumen,
         name='api_delete_dokumen'),
]