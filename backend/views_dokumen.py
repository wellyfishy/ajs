import logging
import mimetypes
import os
import tempfile
import uuid

import boto3
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from backend.models import Client, Dokumen, DokumenTaskLog, Kategori, Shipment
from backend.tasks import task_upload_dokumen

logger = logging.getLogger(__name__)


def is_admin(user):
    return hasattr(user, 'profile') and user.profile.role == 'admin'


# ──────────────────────────────────────────────────────────────
#  Page: Dokumen list + bulk upload form
# ──────────────────────────────────────────────────────────────

@login_required
def dokumen_page(request):
    context = {
        'kategori_list': Kategori.objects.all(),
        'client_list':   Client.objects.all(),
        'shipment_list': Shipment.objects.all().select_related('client'),
        'is_admin':      is_admin(request.user),
    }
    return render(request, 'panel/dokumen/list2.html', context)


# ──────────────────────────────────────────────────────────────
#  API: Bulk upload
# ──────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def api_upload_dokumen(request):
    files       = request.FILES.getlist('files')
    client_id   = request.POST.get('client_id') or None
    shipment_id = request.POST.get('shipment_id') or None
    judul_list  = request.POST.getlist('judul')

    if not files:
        return JsonResponse({'error': 'Tidak ada file yang dipilih.'}, status=400)

    results = []

    for idx, uploaded_file in enumerate(files):
        mime_type = (
            uploaded_file.content_type
            or mimetypes.guess_type(uploaded_file.name)[0]
            or 'application/octet-stream'
        )

        # Build S3 key path
        safe_name = uploaded_file.name.replace(' ', '_')
        ext       = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else 'bin'
        s3_key    = f"dokumen/{timezone.now().strftime('%Y/%m')}/{uuid.uuid4().hex}.{ext}"

        # Create Dokumen record with pending status
        dok = Dokumen.objects.create(
            client_id     = client_id,
            shipment_id   = shipment_id,
            uploaded_by   = request.user,
            nama_file     = uploaded_file.name,
            ukuran        = uploaded_file.size,
            mime_type     = mime_type,
            judul         = judul_list[idx] if idx < len(judul_list) else '',
            upload_status = 'pending',
            ocr_status    = 'pending',
        )
        dok.file.name = s3_key
        dok.save(update_fields=['file'])

        # Write to temp file for Celery worker to read
        tmp_dir  = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, safe_name)
        with open(tmp_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        # Fire upload task
        upload_task = task_upload_dokumen.delay(dok.pk, tmp_path)
        DokumenTaskLog.objects.create(
            dokumen   = dok,
            task_id   = upload_task.id,
            task_type = 'upload',
        )

        results.append({
            'dokumen_id': dok.pk,
            'nama_file':  dok.nama_file,
            'task_id':    upload_task.id,
        })

    return JsonResponse({'uploaded': results})


# ──────────────────────────────────────────────────────────────
#  API: Poll progress (no login required — works after logout)
# ──────────────────────────────────────────────────────────────

def api_dokumen_progress(request, dokumen_id):
    try:
        dok = Dokumen.objects.get(pk=dokumen_id)
    except Dokumen.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)

    return JsonResponse({
        'dokumen_id':      dok.pk,
        'nama_file':       dok.nama_file,
        'upload_status':   dok.upload_status,
        'upload_progress': dok.upload_progress,
        'ocr_status':      dok.ocr_status,
        'ocr_progress':    dok.ocr_progress,
        'ocr_engine':      dok.ocr_engine,
        'kategori':        dok.kategori.judul if dok.kategori_id else None,
    })


# ──────────────────────────────────────────────────────────────
#  API: List dokumen with fuzzy search + filters
# ──────────────────────────────────────────────────────────────

@login_required
def api_list_dokumen(request):
    q           = request.GET.get('q', '').strip()
    page_num    = int(request.GET.get('page', 1))
    per_page    = int(request.GET.get('per_page', 20))
    client_id   = request.GET.get('client_id')
    shipment_id = request.GET.get('shipment_id')
    kategori_id = request.GET.get('kategori_id')

    qs = Dokumen.objects.select_related('kategori', 'client', 'shipment', 'uploaded_by')

    if client_id:
        qs = qs.filter(client_id=client_id)
    if shipment_id:
        qs = qs.filter(shipment_id=shipment_id)
    if kategori_id:
        qs = qs.filter(kategori_id=kategori_id)
    if q:
        qs = _fuzzy_search(qs, q)

    paginator = Paginator(qs, per_page)
    page_obj  = paginator.get_page(page_num)
    user_is_admin = is_admin(request.user)

    items = []
    for dok in page_obj:
        items.append({
            'id':             dok.pk,
            'nama_file':      dok.nama_file,
            'judul':          dok.judul,
            'ukuran':         dok.ukuran,
            'mime_type':      dok.mime_type,
            'kategori':       dok.kategori.judul if dok.kategori_id else '—',
            'client':         dok.client.nama if dok.client_id else '—',
            'shipment':       dok.shipment.nomor_referensi if dok.shipment_id else '—',
            'upload_status':  dok.upload_status,
            'upload_progress': dok.upload_progress,
            'ocr_status':     dok.ocr_status,
            'ocr_progress':   dok.ocr_progress,
            'ocr_engine':     dok.ocr_engine,
            'created_at':     dok.created_at.isoformat(),
            'uploaded_by':    dok.uploaded_by.get_full_name() or dok.uploaded_by.username
                              if dok.uploaded_by else '—',
            'can_view':       user_is_admin,
            'signed_url':     _get_signed_url(dok) if user_is_admin else None,
        })

    return JsonResponse({
        'items':    items,
        'total':    paginator.count,
        'pages':    paginator.num_pages,
        'page':     page_obj.number,
        'has_next': page_obj.has_next(),
        'has_prev': page_obj.has_previous(),
    })


def _fuzzy_search(qs, query: str):
    from django.db.models import Q
    from django.conf import settings as dj_settings

    db_engine = dj_settings.DATABASES['default']['ENGINE']

    if 'postgresql' in db_engine:
        from django.contrib.postgres.search import TrigramSimilarity
        qs = qs.annotate(
            search_rank=(
                TrigramSimilarity('nama_file',  query)
                + TrigramSimilarity('judul',      query)
                + TrigramSimilarity('keterangan', query)
                + TrigramSimilarity('ocr_teks',   query)
            )
        ).filter(search_rank__gt=0.05).order_by('-search_rank')
    else:
        # SQLite fallback
        qs = qs.filter(
            Q(nama_file__icontains=query)
            | Q(judul__icontains=query)
            | Q(keterangan__icontains=query)
            | Q(ocr_teks__icontains=query)
        )

    return qs


def _get_signed_url(dok) -> str | None:
    if not dok.file or not dok.file.name:
        return None
    try:
        from django.conf import settings as dj_settings
        s3 = boto3.client(
            's3',
            aws_access_key_id=dj_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=dj_settings.AWS_SECRET_ACCESS_KEY,
            region_name=dj_settings.AWS_S3_REGION_NAME,
        )
        return s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': dj_settings.AWS_STORAGE_BUCKET_NAME,
                'Key':    dok.file.name,
            },
            ExpiresIn=300,
        )
    except Exception as e:
        logger.error(f"Signed URL error: {e}")
        return None


# ──────────────────────────────────────────────────────────────
#  API: Delete dokumen (admin only)
# ──────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['DELETE'])
def api_delete_dokumen(request, dokumen_id):
    if not is_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    dok = get_object_or_404(Dokumen, pk=dokumen_id)

    # Delete from S3
    try:
        from django.conf import settings as dj_settings
        s3 = boto3.client(
            's3',
            aws_access_key_id=dj_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=dj_settings.AWS_SECRET_ACCESS_KEY,
            region_name=dj_settings.AWS_S3_REGION_NAME,
        )
        s3.delete_object(
            Bucket=dj_settings.AWS_STORAGE_BUCKET_NAME,
            Key=dok.file.name
        )
    except Exception as e:
        logger.warning(f"S3 delete failed: {e}")

    dok.delete()
    return JsonResponse({'deleted': dokumen_id})