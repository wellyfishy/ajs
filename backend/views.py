from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from .models import Profile, TeamMember, TodoList, Client, Layanan, Shipment, Absensi, History, Dokumen
from functools import wraps
from django.http import JsonResponse
import mimetypes
import os
import tempfile
import uuid


from backend.models import Dokumen, DokumenTaskLog
from backend.tasks import task_upload_dokumen

def _handle_dokumen_upload(request, shipment):
    """
    Handles multiple file uploads for a shipment.
    Creates Dokumen records and fires Celery upload+OCR tasks.
    Returns list of created Dokumen PKs.
    """
    files = request.FILES.getlist('dokumen')
    if not files:
        return []

    created = []

    for uploaded_file in files:
        mime_type = (
            uploaded_file.content_type
            or mimetypes.guess_type(uploaded_file.name)[0]
            or 'application/octet-stream'
        )

        safe_name = uploaded_file.name.replace(' ', '_')
        ext       = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else 'bin'
        s3_key    = f"dokumen/{timezone.now().strftime('%Y/%m')}/{uuid.uuid4().hex}.{ext}"

        dok = Dokumen.objects.create(
            shipment      = shipment,
            client        = shipment.client,
            uploaded_by   = request.user,
            nama_file     = uploaded_file.name,
            ukuran        = uploaded_file.size,
            mime_type     = mime_type,
            upload_status = 'pending',
            ocr_status    = 'pending',
        )
        dok.file.name = s3_key
        dok.save(update_fields=['file'])

        # Write to temp file for Celery
        tmp_dir  = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, safe_name)
        with open(tmp_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        upload_task = task_upload_dokumen.delay(dok.pk, tmp_path)
        DokumenTaskLog.objects.create(
            dokumen   = dok,
            task_id   = upload_task.id,
            task_type = 'upload',
        )
        created.append(dok.pk)

    return created

def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            try:
                if request.user.profile.role in roles:
                    return view_func(request, *args, **kwargs)
            except Profile.DoesNotExist:
                pass
            messages.error(request, 'Anda tidak memiliki akses ke halaman ini.')
            return redirect('index')
        return wrapper
    return decorator

def log_history(user, aksi, detail):
    History.objects.create(user=user, aksi=aksi, detail=detail)

# ── LANDING PAGE ──
def index(request):
    layanan = Layanan.objects.filter(aktif=True).order_by('-pk')
    team = TeamMember.objects.filter(aktif=True).order_by('urutan')
    context = {
        'layanan': layanan,
        'team': team,
    }
    return render(request, 'landing/index.html', context)

def about(request):
    return render(request, 'landing/about.html')

def teams(request):
    team = TeamMember.objects.filter(aktif=True).order_by('urutan')
    return render(request, 'landing/teams.html', {'team': team})

# ── AUTH ──
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            log_history(user, 'LOGIN', f'{user.username} login')
            return redirect('dashboard')
        messages.error(request, 'Username atau password salah.')
    return render(request, 'auth/login.html')

@login_required
def logout_view(request):
    log_history(request.user, 'LOGOUT', f'{request.user.username} logout')
    logout(request)
    return redirect('index')


# ── DASHBOARD ──
@login_required
def dashboard(request):
    todo_count = TodoList.objects.filter(status='pending').count()
    shipment_count = Shipment.objects.filter(status='proses').count()
    history = History.objects.order_by('-created_at')[:10]
    today = timezone.now().date()
    absen_today = Absensi.objects.filter(user=request.user, tanggal=today).first()
    context = {
        'todo_count': todo_count,
        'shipment_count': shipment_count,
        'history': history,
        'absen_today': absen_today,
    }
    return render(request, 'panel/dashboard.html', context)


# ── TEAM CRUD ──
@login_required
@role_required('admin')
def team_list(request):
    team = TeamMember.objects.all().order_by('urutan')
    return render(request, 'panel/team/list.html', {'team': team})


@login_required
@role_required('admin')
def team_create(request):
    if request.method == 'POST':
        member = TeamMember.objects.create(
            nama=request.POST.get('nama'),
            jabatan=request.POST.get('jabatan'),
            bio=request.POST.get('bio'),
            urutan=request.POST.get('urutan', 0),
            aktif=request.POST.get('aktif') == 'on',
            foto=request.FILES.get('foto'),
        )
        log_history(request.user, 'CREATE', f'Tambah team member: {member.nama}')
        messages.success(request, 'Team member berhasil ditambahkan.')
        return redirect('team_list')
    return render(request, 'panel/team/form.html')


@login_required
@role_required('admin')
def team_edit(request, pk):
    member = get_object_or_404(TeamMember, pk=pk)
    if request.method == 'POST':
        member.nama = request.POST.get('nama')
        member.jabatan = request.POST.get('jabatan')
        member.bio = request.POST.get('bio')
        member.urutan = request.POST.get('urutan', 0)
        member.aktif = request.POST.get('aktif') == 'on'
        if request.FILES.get('foto'):
            member.foto = request.FILES.get('foto')
        member.save()
        log_history(request.user, 'EDIT', f'Edit team member: {member.nama}')
        messages.success(request, 'Team member berhasil diupdate.')
        return redirect('team_list')
    return render(request, 'panel/team/form.html', {'member': member})


@login_required
@role_required('admin')
def team_delete(request, pk):
    member = get_object_or_404(TeamMember, pk=pk)
    log_history(request.user, 'DELETE', f'Hapus team member: {member.nama}')
    member.delete()
    messages.success(request, 'Team member berhasil dihapus.')
    return redirect('team_list')


# ── TODO CRUD ──
@login_required
def todo_list(request):
    todos = TodoList.objects.all().order_by('-created_at')
    return render(request, 'panel/todo/list.html', {'todos': todos})


@login_required
def todo_create(request):
    if request.method == 'POST':
        todo = TodoList.objects.create(
            judul=request.POST.get('judul'),
            deskripsi=request.POST.get('deskripsi'),
            status=request.POST.get('status', 'pending'),
            dibuat_oleh=request.user,
            deadline=request.POST.get('deadline') or None,
            ditugaskan_ke=User.objects.filter(pk=request.POST.get('ditugaskan_ke')).first(),
        )
        log_history(request.user, 'CREATE', f'Tambah todo: {todo.judul}')
        messages.success(request, 'Todo berhasil ditambahkan.')
        return redirect('todo_list')
    users = User.objects.all()
    return render(request, 'panel/todo/form.html', {'users': users})


@login_required
def todo_edit(request, pk):
    todo = get_object_or_404(TodoList, pk=pk)
    if request.method == 'POST':
        todo.judul = request.POST.get('judul')
        todo.deskripsi = request.POST.get('deskripsi')
        todo.status = request.POST.get('status', 'pending')
        todo.deadline = request.POST.get('deadline') or None
        todo.ditugaskan_ke = User.objects.filter(pk=request.POST.get('ditugaskan_ke')).first()
        todo.save()
        log_history(request.user, 'EDIT', f'Edit todo: {todo.judul}')
        messages.success(request, 'Todo berhasil diupdate.')
        return redirect('todo_list')
    users = User.objects.all()
    return render(request, 'panel/todo/form.html', {'todo': todo, 'users': users})


@login_required
def todo_delete(request, pk):
    todo = get_object_or_404(TodoList, pk=pk)
    log_history(request.user, 'DELETE', f'Hapus todo: {todo.judul}')
    todo.delete()
    messages.success(request, 'Todo berhasil dihapus.')
    return redirect('todo_list')

@login_required
def todo_status(request, pk):
    """AJAX endpoint — update todo status without full page reload."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)
 
    todo = get_object_or_404(TodoList, pk=pk)
    new_status = request.POST.get('status', '').strip()
 
    valid_statuses = dict(TodoList.STATUS_CHOICES).keys()
    if new_status not in valid_statuses:
        return JsonResponse({'ok': False, 'error': 'Status tidak valid'}, status=400)
 
    old_status = todo.get_status_display()
    todo.status = new_status
    todo.save(update_fields=['status', 'updated_at'])
 
    log_history(
        request.user,
        'EDIT',
        f'Update status todo "{todo.judul}": {old_status} → {todo.get_status_display()}'
    )
 
    return JsonResponse({
        'ok': True,
        'pk': todo.pk,
        'status': todo.status,
        'status_display': todo.get_status_display(),
    })

# ── CLIENT CRUD ──
@login_required
@role_required('admin', 'karyawan')
def client_list(request):
    clients = Client.objects.all().order_by('-created_at')
    return render(request, 'panel/client/list.html', {'clients': clients})


@login_required
@role_required('admin', 'karyawan')
def client_create(request):
    if request.method == 'POST':
        client = Client.objects.create(
            nama=request.POST.get('nama'),
            perusahaan=request.POST.get('perusahaan'),
            email=request.POST.get('email'),
            no_hp=request.POST.get('no_hp'),
            alamat=request.POST.get('alamat'),
        )
        log_history(request.user, 'CREATE', f'Tambah client: {client.nama}')
        messages.success(request, 'Client berhasil ditambahkan.')
        return redirect('client_list')
    return render(request, 'panel/client/form.html')


@login_required
@role_required('admin', 'karyawan')
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.nama = request.POST.get('nama')
        client.perusahaan = request.POST.get('perusahaan')
        client.email = request.POST.get('email')
        client.no_hp = request.POST.get('no_hp')
        client.alamat = request.POST.get('alamat')
        client.save()
        log_history(request.user, 'EDIT', f'Edit client: {client.nama}')
        messages.success(request, 'Client berhasil diupdate.')
        return redirect('client_list')
    return render(request, 'panel/client/form.html', {'client': client})


@login_required
@role_required('admin')
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    log_history(request.user, 'DELETE', f'Hapus client: {client.nama}')
    client.delete()
    messages.success(request, 'Client berhasil dihapus.')
    return redirect('client_list')


# ── LAYANAN CRUD ──
@login_required
@role_required('admin')
def layanan_list(request):
    layanan = Layanan.objects.all().order_by('-pk')
    return render(request, 'panel/layanan/list.html', {'layanan': layanan})

@login_required
@role_required('admin')
def layanan_create(request):
    if request.method == 'POST':
        l = Layanan.objects.create(
            nama=request.POST.get('nama'),
            emoji=request.POST.get('emoji'),
            deskripsi=request.POST.get('deskripsi'),
            aktif=request.POST.get('aktif') == 'on',
        )
        log_history(request.user, 'CREATE', f'Tambah layanan: {l.nama}')
        messages.success(request, 'Layanan berhasil ditambahkan.')
        return redirect('layanan_list')
    return render(request, 'panel/layanan/form.html')


@login_required
@role_required('admin')
def layanan_edit(request, pk):
    layanan = get_object_or_404(Layanan, pk=pk)
    if request.method == 'POST':
        layanan.nama = request.POST.get('nama')
        layanan.emoji = request.POST.get('emoji')
        layanan.deskripsi = request.POST.get('deskripsi')
        layanan.aktif = request.POST.get('aktif') == 'on'
        layanan.save()
        log_history(request.user, 'EDIT', f'Edit layanan: {layanan.nama}')
        messages.success(request, 'Layanan berhasil diupdate.')
        return redirect('layanan_list')
    return render(request, 'panel/layanan/form.html', {'layanan': layanan})


@login_required
@role_required('admin')
def layanan_delete(request, pk):
    layanan = get_object_or_404(Layanan, pk=pk)
    log_history(request.user, 'DELETE', f'Hapus layanan: {layanan.nama}')
    layanan.delete()
    messages.success(request, 'Layanan berhasil dihapus.')
    return redirect('layanan_list')

# ── SHIPMENT CRUD ──
@login_required
@role_required('admin', 'karyawan')
def shipment_list(request):
    shipments = Shipment.objects.all().order_by('-created_at')
    return render(request, 'panel/shipment/list.html', {'shipments': shipments})

@login_required
@role_required('admin', 'karyawan')
def shipment_status(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)

    shipment = get_object_or_404(Shipment, pk=pk)
    new_status = request.POST.get('status', '').strip()

    valid_statuses = dict(Shipment.STATUS_CHOICES).keys()
    if new_status not in valid_statuses:
        return JsonResponse({'ok': False, 'error': 'Status tidak valid'}, status=400)

    old_status = shipment.get_status_display()
    shipment.status = new_status
    shipment.save(update_fields=['status', 'updated_at'])

    # ── Sync TodoList status ──────────────────────────────────
    STATUS_MAP = {
        'pending': 'pending',
        'proses':  'in_progress',
        'selesai': 'done',
        'batal':   'cancel',
    }
    todo_status = STATUS_MAP.get(new_status)
    if todo_status:
        updated = TodoList.objects.filter(shipment=shipment).update(
            status     = todo_status,
            updated_at = timezone.now(),
        )

    log_history(
        request.user,
        'EDIT',
        f'Update status {shipment.nomor_referensi}: {old_status} → {shipment.get_status_display()}'
    )

    return JsonResponse({
        'ok':             True,
        'pk':             shipment.pk,
        'status':         shipment.status,
        'status_display': shipment.get_status_display(),
    })

@login_required
@role_required('admin', 'karyawan')
def shipment_create(request):
    if request.method == 'POST':
        shipment = Shipment.objects.create(
            nomor_referensi  = request.POST.get('nomor_referensi'),
            client           = Client.objects.filter(pk=request.POST.get('client')).first(),
            layanan          = Layanan.objects.filter(pk=request.POST.get('layanan')).first(),
            deskripsi        = request.POST.get('deskripsi'),
            status           = request.POST.get('status', 'pending'),
            pic              = User.objects.filter(pk=request.POST.get('pic')).first(),
            tanggal_request  = request.POST.get('tanggal_request') or timezone.now().date(),
            tanggal_selesai  = request.POST.get('tanggal_selesai') or None,
            tanggal_deadline = request.POST.get('tanggal_deadline') or None,
            catatan          = request.POST.get('catatan'),
        )
        # ── Handle multiple dokumen uploads ──────────────────
        _handle_dokumen_upload(request, shipment)

        TodoList.objects.create(
            judul        = f'Shipment: {shipment.nomor_referensi}',
            deskripsi    = (
                f'Layanan: {shipment.layanan}\n'
                f'Tgl Request: {shipment.tanggal_request}\n\n'
                f'Deskripsi: {shipment.deskripsi or "-"}'
            ),
            status       = shipment.status,
            dibuat_oleh  = request.user,
            deadline     = shipment.tanggal_deadline,
            ditugaskan_ke = None,
            shipment     = shipment,
        )
        log_history(request.user, 'CREATE', f'Tambah shipment: {shipment.nomor_referensi}')
        messages.success(request, 'Shipment berhasil ditambahkan.')
        return redirect('shipment_list')
    clients = Client.objects.all()
    layanan = Layanan.objects.filter(aktif=True)
    users = User.objects.all()
    return render(request, 'panel/shipment/form.html', {'clients': clients, 'layanan': layanan, 'users': users})

@login_required
@role_required('admin', 'karyawan')
def shipment_edit(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk)

    if request.method == 'POST':
        shipment.nomor_referensi  = request.POST.get('nomor_referensi')
        shipment.client           = Client.objects.filter(pk=request.POST.get('client')).first()
        shipment.layanan          = Layanan.objects.filter(pk=request.POST.get('layanan')).first()
        shipment.deskripsi        = request.POST.get('deskripsi')
        shipment.status           = request.POST.get('status', 'pending')
        shipment.pic              = User.objects.filter(pk=request.POST.get('pic')).first()
        shipment.tanggal_request  = request.POST.get('tanggal_request') or timezone.now().date()
        shipment.tanggal_selesai  = request.POST.get('tanggal_selesai') or None
        shipment.tanggal_deadline = request.POST.get('tanggal_deadline') or None
        shipment.catatan          = request.POST.get('catatan')
        shipment.save()

        # ── Sync TodoList status ──────────────────────────────
        STATUS_MAP = {
            'pending': 'pending',
            'proses':  'in_progress',
            'selesai': 'done',
            'batal':   'cancel',
        }
        todo_status = STATUS_MAP.get(shipment.status)
        if todo_status:
            TodoList.objects.filter(shipment=shipment).update(
                status     = todo_status,
                updated_at = timezone.now(),
            )

        # ── Handle new dokumen uploads ────────────────────────
        _handle_dokumen_upload(request, shipment)

        log_history(request.user, 'EDIT', f'Edit shipment: {shipment.nomor_referensi}')
        messages.success(request, 'Shipment berhasil diupdate.')
        return redirect('shipment_list')

    clients          = Client.objects.all()
    layanan          = Layanan.objects.filter(aktif=True)
    users            = User.objects.all()
    existing_dokumen = Dokumen.objects.filter(shipment=shipment).select_related('kategori')

    return render(request, 'panel/shipment/form.html', {
        'shipment':          shipment,
        'clients':           clients,
        'layanan':           layanan,
        'users':             users,
        'existing_dokumen':  existing_dokumen,
    })

@login_required
@role_required('admin', 'karyawan')
def shipment_delete(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk)

    # TodoList akan otomatis terhapus karena CASCADE di ForeignKey
    # tapi kita log dulu sebelum dihapus
    nomor_ref = shipment.nomor_referensi

    shipment.delete()  # CASCADE: TodoList + Dokumen records ikut terhapus dari DB

    log_history(request.user, 'DELETE', f'Hapus shipment: {nomor_ref}')
    messages.success(request, f'Shipment {nomor_ref} berhasil dihapus.')
    return redirect('shipment_list')

# ── ABSENSI ──
@login_required
def absensi_list(request):
    if request.user.profile.role == 'admin':
        absensi = Absensi.objects.all().order_by('-tanggal')
    else:
        absensi = Absensi.objects.filter(user=request.user).order_by('-tanggal')
    return render(request, 'panel/absensi/list.html', {'absensi': absensi})


@login_required
def absen_masuk(request):
    today = timezone.now().date()
    absen, created = Absensi.objects.get_or_create(
        user=request.user,
        tanggal=today,
        defaults={'jam_masuk': timezone.now().time(), 'status': 'hadir'}
    )
    if created:
        log_history(request.user, 'ABSEN', f'{request.user.username} absen masuk pukul {absen.jam_masuk}')
        messages.success(request, f'Absen masuk berhasil pukul {absen.jam_masuk}.')
    else:
        messages.warning(request, 'Anda sudah absen hari ini.')
    return redirect('dashboard')


@login_required
def absen_keluar(request):
    today = timezone.now().date()
    absen = Absensi.objects.filter(user=request.user, tanggal=today).first()
    if absen and not absen.jam_keluar:
        absen.jam_keluar = timezone.now().time()
        absen.save()
        log_history(request.user, 'ABSEN', f'{request.user.username} absen keluar pukul {absen.jam_keluar}')
        messages.success(request, f'Absen keluar berhasil pukul {absen.jam_keluar}.')
    else:
        messages.warning(request, 'Anda belum absen masuk atau sudah absen keluar.')
    return redirect('dashboard')


# ── DOKUMEN ──
@login_required
def dokumen_list(request):
    return render(request, 'panel/dokumen/list.html')


# ── USER MANAGEMENT (admin only) ──
@login_required
@role_required('admin')
def user_list(request):
    users = User.objects.all().select_related('profile')
    return render(request, 'panel/user/list.html', {'users': users})


@login_required
@role_required('admin')
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email')
        role = request.POST.get('role', 'karyawan')
        user = User.objects.create_user(username=username, password=password, email=email)
        Profile.objects.create(
            user=user,
            role=role,
            jabatan=request.POST.get('jabatan'),
            no_hp=request.POST.get('no_hp'),
            foto=request.FILES.get('foto'),
        )
        log_history(request.user, 'CREATE', f'Tambah user: {username} role: {role}')
        messages.success(request, 'User berhasil ditambahkan.')
        return redirect('user_list')
    return render(request, 'panel/user/form.html')


@login_required
@role_required('admin')
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    profile, _ = Profile.objects.get_or_create(user=user)
    if request.method == 'POST':
        user.email = request.POST.get('email')
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        if request.POST.get('password'):
            user.set_password(request.POST.get('password'))
        user.save()
        profile.role = request.POST.get('role', profile.role)
        profile.jabatan = request.POST.get('jabatan')
        profile.no_hp = request.POST.get('no_hp')
        if request.FILES.get('foto'):
            profile.foto = request.FILES.get('foto')
        profile.save()
        log_history(request.user, 'EDIT', f'Edit user: {user.username}')
        messages.success(request, 'User berhasil diupdate.')
        return redirect('user_list')
    return render(request, 'panel/user/form.html', {'edit_user': user, 'profile': profile})


@login_required
@role_required('admin')
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    log_history(request.user, 'DELETE', f'Hapus user: {user.username}')
    user.delete()
    messages.success(request, 'User berhasil dihapus.')
    return redirect('user_list')


# ── HISTORY ──
@login_required
@role_required('admin')
def history_list(request):
    history = History.objects.all().order_by('-created_at')
    return render(request, 'panel/history/list.html', {'history': history})