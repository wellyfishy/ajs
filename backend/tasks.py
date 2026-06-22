import logging
import os
from io import BytesIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Helpers — Text Extraction
# ──────────────────────────────────────────────────────────────
def _extract_via_textract_s3(s3_key: str) -> str:
    """
    Textract extraction for S3 documents.
    - Single page: uses sync detect_document_text (fast)
    - Multi page:  uses async start_document_text_detection (handles all pages)
    """
    import time

    client = boto3.client(
        'textract',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_TEXTRACT_REGION,
    )

    # ── Try sync first (works for single-page, faster) ────────
    try:
        response = client.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Name':   s3_key,
                }
            }
        )
        lines = [
            block['Text']
            for block in response['Blocks']
            if block['BlockType'] == 'LINE'
        ]
        text = '\n'.join(lines)
        if text.strip():
            return text
        # Empty result — fall through to async (might be multi-page)

    except client.exceptions.UnsupportedDocumentException:
        logger.warning(f"Textract sync: unsupported format for {s3_key}")
        return ''
    except client.exceptions.InvalidParameterException:
        # Multi-page PDF — sync doesn't support it, fall through to async
        logger.info(f"Textract sync failed (likely multi-page), switching to async: {s3_key}")
    except Exception as e:
        logger.warning(f"Textract sync error for {s3_key}: {e}, trying async...")

    # ── Async for multi-page PDFs ──────────────────────────────
    try:
        # Start async job
        start_response = client.start_document_text_detection(
            DocumentLocation={
                'S3Object': {
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Name':   s3_key,
                }
            }
        )
        job_id = start_response['JobId']
        logger.info(f"Textract async job started: {job_id} for {s3_key}")

        # Poll until complete (max 5 minutes)
        max_wait  = 300
        waited    = 0
        poll_interval = 3

        while waited < max_wait:
            result = client.get_document_text_detection(JobId=job_id)
            status = result['JobStatus']

            if status == 'SUCCEEDED':
                break
            elif status == 'FAILED':
                logger.error(f"Textract async job failed for {s3_key}: "
                             f"{result.get('StatusMessage', 'unknown')}")
                return ''

            time.sleep(poll_interval)
            waited += poll_interval

        if waited >= max_wait:
            logger.error(f"Textract async job timed out for {s3_key}")
            return ''

        # Collect all pages (paginated results)
        all_lines = []
        next_token = None

        while True:
            if next_token:
                page_result = client.get_document_text_detection(
                    JobId=job_id,
                    NextToken=next_token
                )
            else:
                page_result = result  # reuse last result from polling

            all_lines.extend([
                block['Text']
                for block in page_result.get('Blocks', [])
                if block['BlockType'] == 'LINE'
            ])

            next_token = page_result.get('NextToken')
            if not next_token:
                break

        text = '\n'.join(all_lines)
        logger.info(f"Textract async extracted {len(all_lines)} lines "
                    f"from {s3_key}")
        return text

    except client.exceptions.UnsupportedDocumentException:
        logger.warning(f"Textract async: unsupported format for {s3_key}")
        return ''
    except Exception as e:
        logger.error(f"Textract async error for {s3_key}: {e}")
        return ''


def _extract_via_textract_bytes(file_bytes: bytes) -> str:
    """Fallback for images under 5MB — send bytes directly instead of S3 reference."""
    try:
        client = boto3.client(
            'textract',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_TEXTRACT_REGION,
        )
        response = client.detect_document_text(
            Document={'Bytes': file_bytes}
        )
        lines = [
            block['Text']
            for block in response['Blocks']
            if block['BlockType'] == 'LINE'
        ]
        return '\n'.join(lines)

    except Exception as e:
        logger.error(f"Textract bytes error: {e}")
        return ''


def _smart_extract(file_bytes: bytes, mime_type: str, s3_key: str) -> tuple[str, str]:
    """
    All documents go through Textract.
    Images under 5MB are sent as bytes; everything else via S3 reference.
    """
    if mime_type.startswith('image/') and len(file_bytes) <= 5 * 1024 * 1024:
        # Small images — send bytes directly (no need for S3 round-trip)
        text = _extract_via_textract_bytes(file_bytes)
    else:
        # PDFs (digital, scanned, mixed) and large images — via S3
        text = _extract_via_textract_s3(s3_key)

    if not text.strip():
        logger.warning(f"Textract returned empty text for {s3_key}")

    return text, 'textract'

# ──────────────────────────────────────────────────────────────
#  Helper — TF-IDF Classification
# ──────────────────────────────────────────────────────────────

def _classify(text: str, kategori_list: list) -> tuple:
    """
    Cosine similarity between doc text and each Kategori.
    Returns (best_kategori_id or None, scores_dict).
    """
    if not text.strip() or not kategori_list:
        return None, {}
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        kat_texts = [f"{k['judul']} {k['deskripsi'] or ''}" for k in kategori_list]
        corpus    = [text] + kat_texts

        vectorizer = TfidfVectorizer(
            analyzer='word',
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(corpus)
        sims   = cosine_similarity(matrix[0:1], matrix[1:]).flatten()

        scores   = {kategori_list[i]['id']: float(sims[i]) for i in range(len(kategori_list))}
        best_idx = int(np.argmax(sims))

        if sims[best_idx] >= 0.01:
            return kategori_list[best_idx]['id'], scores
        return None, scores

    except Exception as e:
        logger.error(f"TF-IDF error: {e}")
        return None, {}


# ──────────────────────────────────────────────────────────────
#  Helper — S3 client
# ──────────────────────────────────────────────────────────────

def _s3():
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )


# ──────────────────────────────────────────────────────────────
#  Task 1 — Upload to S3
# ──────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def task_upload_dokumen(self, dokumen_id: int, tmp_file_path: str):
    from backend.models import Dokumen, DokumenTaskLog

    try:
        dok = Dokumen.objects.get(pk=dokumen_id)
        dok.upload_status   = 'uploading'
        dok.upload_progress = 0
        dok.save(update_fields=['upload_status', 'upload_progress'])

        s3        = _s3()
        bucket    = settings.AWS_STORAGE_BUCKET_NAME
        s3_key    = dok.file.name
        file_size = os.path.getsize(tmp_file_path)

        # Progress callback updates DB every chunk
        class Progress:
            uploaded = 0
            def __call__(self, amount):
                self.uploaded += amount
                pct = min(int(self.uploaded / file_size * 100), 99)
                Dokumen.objects.filter(pk=dokumen_id).update(upload_progress=pct)

        with open(tmp_file_path, 'rb') as f:
            s3.upload_fileobj(
                f, bucket, s3_key,
                Callback=Progress(),
                ExtraArgs={
                    'ContentType':            dok.mime_type or 'application/octet-stream',
                    'ServerSideEncryption':   'AES256',
                }
            )

        dok.upload_status   = 'uploaded'
        dok.upload_progress = 100
        dok.save(update_fields=['upload_status', 'upload_progress'])

        # Clean up temp file
        try:
            os.remove(tmp_file_path)
        except OSError:
            pass

        # Chain into OCR task immediately
        ocr_task = task_ocr_and_classify.delay(dokumen_id)
        DokumenTaskLog.objects.create(
            dokumen_id=dokumen_id,
            task_id=ocr_task.id,
            task_type='ocr',
        )

    except Dokumen.DoesNotExist:
        logger.error(f"Dokumen {dokumen_id} not found")
    except (BotoCoreError, ClientError) as exc:
        Dokumen.objects.filter(pk=dokumen_id).update(
            upload_status='failed',
            upload_error=str(exc),
        )
        raise self.retry(exc=exc)
    except Exception as exc:
        Dokumen.objects.filter(pk=dokumen_id).update(
            upload_status='failed',
            upload_error=str(exc),
        )
        logger.exception(f"Upload failed for Dokumen {dokumen_id}")
        raise


# ──────────────────────────────────────────────────────────────
#  Task 2 — OCR + Classification
# ──────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def task_ocr_and_classify(self, dokumen_id: int):
    from backend.models import Dokumen, Kategori

    try:
        dok = Dokumen.objects.get(pk=dokumen_id)
        dok.ocr_status   = 'processing'
        dok.ocr_progress = 5
        dok.save(update_fields=['ocr_status', 'ocr_progress'])

        # ── 1. Download from S3 ──────────────────────────────
        buffer = BytesIO()
        _s3().download_fileobj(
            settings.AWS_STORAGE_BUCKET_NAME,
            dok.file.name,
            buffer
        )
        file_bytes = buffer.getvalue()

        dok.ocr_progress = 20
        dok.save(update_fields=['ocr_progress'])

        # ── 2. Smart extraction (PyMuPDF or Textract) ────────
        text, engine = _smart_extract(file_bytes, dok.mime_type, dok.file.name)

        dok.ocr_teks   = text
        dok.ocr_engine = engine
        dok.ocr_progress = 70
        dok.save(update_fields=['ocr_teks', 'ocr_engine', 'ocr_progress'])

        # ── 3. TF-IDF Classification ─────────────────────────
        kategori_qs   = Kategori.objects.all().values('id', 'judul', 'deskripsi')
        kategori_list = list(kategori_qs)

        best_kat_id, scores = _classify(text, kategori_list)

        # NEW — safe against duplicates
        if best_kat_id is None:
            tidak_ada = Kategori.objects.filter(judul='Tidak Ada').first()
            if not tidak_ada:
                tidak_ada = Kategori.objects.create(
                    judul='Tidak Ada',
                    deskripsi='Dokumen tidak dapat diklasifikasikan'
                )
            best_kat_id = tidak_ada.pk

        dok.kategori_id  = best_kat_id
        dok.tfidf_scores = scores
        dok.ocr_status   = 'done'
        dok.ocr_progress = 100
        dok.save(update_fields=['kategori_id', 'tfidf_scores', 'ocr_status', 'ocr_progress'])

        logger.info(f"Dokumen {dokumen_id} processed via {engine}, "
                    f"kategori: {dok.kategori.judul}")

    except Dokumen.DoesNotExist:
        logger.error(f"Dokumen {dokumen_id} not found for OCR")
    except Exception as exc:
        Dokumen.objects.filter(pk=dokumen_id).update(
            ocr_status='failed',
            ocr_error=str(exc),
        )
        logger.exception(f"OCR failed for Dokumen {dokumen_id}")
        raise self.retry(exc=exc)