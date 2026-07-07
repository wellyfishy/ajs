from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
from backend.storage_backends import DokumenS3Storage


class Profile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('karyawan', 'Karyawan'),
        ('guest', 'Guest'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='guest')
    foto = models.ImageField(
        upload_to='foto_profil/',
        storage=DokumenS3Storage(),   # <-- tambahkan ini
        null=True, blank=True
    )
    jabatan = models.CharField(max_length=100, null=True, blank=True)
    no_hp = models.CharField(max_length=20, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)

    def __str__(self):
        return f'{self.user.username} - {self.role}'


class TeamMember(models.Model):
    nama = models.CharField(max_length=100)
    jabatan = models.CharField(max_length=100)
    foto = models.ImageField(
        upload_to='foto_team/',
        storage=DokumenS3Storage(),   # <-- tambahkan ini
        null=True, blank=True
    )
    bio = models.TextField(null=True, blank=True)
    urutan = models.IntegerField(default=0)
    aktif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.nama} - {self.jabatan}'

class Client(models.Model):
    nama = models.CharField(max_length=200)
    perusahaan = models.CharField(max_length=200, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    no_hp = models.CharField(max_length=20, null=True, blank=True)
    alamat = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nama

class Layanan(models.Model):
    nama = models.CharField(max_length=200)
    emoji = models.CharField(max_length=100, null=True, blank=True)
    deskripsi = models.TextField(null=True, blank=True)
    aktif = models.BooleanField(default=True)

    def __str__(self):
        return self.nama

class Shipment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('proses', 'Dalam Proses'),
        ('selesai', 'Selesai'),
        ('batal', 'Dibatalkan'),
    ]
    nomor_referensi = models.CharField(max_length=100, unique=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True)
    layanan = models.ForeignKey(Layanan, on_delete=models.SET_NULL, null=True)
    deskripsi = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    pic = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tanggal_request = models.DateField(default=timezone.now)
    tanggal_selesai = models.DateField(null=True, blank=True)
    tanggal_deadline = models.DateField(null=True, blank=True)
    catatan = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.nomor_referensi} - {self.client}'
    
class TodoList(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancel')
    ]
    judul = models.CharField(max_length=200)
    deskripsi = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='todo_dibuat')
    ditugaskan_ke = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='todo_ditugaskan')
    deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, null=True, blank=True, related_name='todo_shipment')

    def __str__(self):
        return self.judul

class Absensi(models.Model):
    STATUS_CHOICES = [
        ('hadir', 'Hadir'),
        ('izin', 'Izin'),
        ('sakit', 'Sakit'),
        ('alpha', 'Alpha'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tanggal = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='hadir')
    jam_masuk = models.TimeField(null=True, blank=True)
    jam_keluar = models.TimeField(null=True, blank=True)
    keterangan = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'tanggal']

    def __str__(self):
        return f'{self.user.username} - {self.tanggal} - {self.status}'


class History(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    aksi = models.CharField(max_length=50)
    detail = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} - {self.aksi} - {self.created_at}'
    
# Add this import at the top of models.py alongside existing imports
import uuid
from backend.storage_backends import DokumenS3Storage


# ── Replace your existing Kategori ───────────────────────────
class Kategori(models.Model):
    judul      = models.CharField(max_length=100)
    deskripsi  = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.judul

    class Meta:
        verbose_name_plural = 'Kategori'
        ordering = ['judul']


# ── Upload path helper ────────────────────────────────────────
def dokumen_upload_path(instance, filename):
    ext         = filename.rsplit('.', 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    return f"{timezone.now().strftime('%Y/%m')}/{unique_name}"


# ── Replace your existing Dokumen ───────────────────────────-
class Dokumen(models.Model):
    UPLOAD_STATUS = [
        ('pending',   'Menunggu Upload'),
        ('uploading', 'Sedang Upload'),
        ('uploaded',  'Terupload'),
        ('failed',    'Gagal'),
    ]
    OCR_STATUS = [
        ('pending',    'Menunggu OCR'),
        ('processing', 'Sedang Diproses'),
        ('done',       'Selesai'),
        ('failed',     'Gagal'),
    ]

    # ── Relations ─────────────────────────────────────────────
    client      = models.ForeignKey(Client,   null=True, blank=True, on_delete=models.SET_NULL)
    shipment    = models.ForeignKey(Shipment, null=True, blank=True, on_delete=models.SET_NULL)
    kategori    = models.ForeignKey(Kategori, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_by = models.ForeignKey(User,     null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='dokumen_diupload')

    # ── File ──────────────────────────────────────────────────
    file      = models.FileField(
        upload_to=dokumen_upload_path,
        storage=DokumenS3Storage(),
        null=True, blank=True
    )
    nama_file = models.CharField(max_length=500, blank=True)
    ukuran    = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)

    # ── Upload status ─────────────────────────────────────────
    upload_status   = models.CharField(max_length=20, choices=UPLOAD_STATUS, default='pending')
    upload_progress = models.IntegerField(default=0)
    upload_error    = models.TextField(blank=True)

    # ── OCR status ────────────────────────────────────────────
    ocr_status    = models.CharField(max_length=20, choices=OCR_STATUS, default='pending')
    ocr_progress  = models.IntegerField(default=0)
    ocr_teks      = models.TextField(blank=True)
    ocr_error     = models.TextField(blank=True)
    ocr_engine    = models.CharField(max_length=20, blank=True)  # 'pymupdf' or 'textract'
    tfidf_scores  = models.JSONField(default=dict, blank=True)

    # ── Metadata ──────────────────────────────────────────────
    judul      = models.CharField(max_length=500, blank=True)
    keterangan = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nama_file or str(self.pk)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['upload_status']),
            models.Index(fields=['ocr_status']),
            models.Index(fields=['kategori']),
            models.Index(fields=['client']),
            models.Index(fields=['shipment']),
            models.Index(fields=['created_at']),
        ]


class DokumenTaskLog(models.Model):
    dokumen    = models.ForeignKey(Dokumen, on_delete=models.CASCADE, related_name='task_logs')
    task_id    = models.CharField(max_length=255, db_index=True)
    task_type  = models.CharField(max_length=50)   # 'upload' | 'ocr'
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.task_type} — {self.task_id}"