from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Profile, TeamMember, TodoList, Client, Layanan, Shipment, Absensi, History, Dokumen, Kategori

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'jabatan', 'no_hp']
    list_filter = ['role']
    search_fields = ['user__username', 'jabatan']

@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ['nama', 'jabatan', 'urutan', 'aktif']
    list_filter = ['aktif']
    search_fields = ['nama', 'jabatan']

@admin.register(TodoList)
class TodoListAdmin(admin.ModelAdmin):
    list_display = ['judul', 'status', 'dibuat_oleh', 'ditugaskan_ke', 'deadline']
    list_filter = ['status']
    search_fields = ['judul']

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['nama', 'perusahaan', 'email', 'no_hp']
    search_fields = ['nama', 'perusahaan']

@admin.register(Layanan)
class LayananAdmin(admin.ModelAdmin):
    list_display = ['nama', 'aktif']
    list_filter = ['aktif']

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ['nomor_referensi', 'client', 'layanan', 'status', 'pic', 'tanggal_request']
    list_filter = ['status']
    search_fields = ['nomor_referensi', 'client__nama']

@admin.register(Absensi)
class AbsensiAdmin(admin.ModelAdmin):
    list_display = ['user', 'tanggal', 'status', 'jam_masuk', 'jam_keluar']
    list_filter = ['status', 'tanggal']
    search_fields = ['user__username']

@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'aksi', 'detail', 'created_at']
    list_filter = ['aksi']
    search_fields = ['user__username', 'detail']
    readonly_fields = ['user', 'aksi', 'detail', 'created_at']

admin.site.register(Dokumen)
admin.site.register(Kategori)