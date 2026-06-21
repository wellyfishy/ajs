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

def _extract_digital_pdf(file_bytes: bytes) -> str:
    """
    PyMuPDF: extracts embedded text from digital PDFs.
    Instant, free, no API call needed.
    """
    try:
        import fitz  # PyMuPDF
        doc  = fitz.open(stream=file_bytes, filetype='pdf')
        text = '\n'.join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        logger.error(f"PyMuPDF extraction error: {e}")
        return ''


def _extract_via_textract_s3(s3_key: str) -> str:
    """
    Amazon Textract: for scanned PDFs already uploaded to S3.
    Handles multi-page docs, best accuracy for scanned content.
    """
    try:
        client = boto3.client(
            'textract',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_TEXTRACT_REGION,
        )
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
        return '\n'.join(lines)
    except Exception as e:
        logger.error(f"Textract (S3) error: {e}")
        return ''


def _extract_via_textract_bytes(file_bytes: bytes) -> str:
    """
    Amazon Textract: for images sent directly as bytes.
    Used for jpg/png uploads (max 5MB per Textract limit).
    """
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
        logger.error(f"Textract (bytes) error: {e}")
        return ''


def _smart_extract(file_bytes: bytes, mime_type: str, s3_key: str) -> tuple[str, str]:
    """
    Smart extraction pipeline:
    1. Digital PDF → PyMuPDF (instant, free)
    2. Scanned PDF → Textract via S3 (accurate, paid)
    3. Image → Textract via bytes (accurate, paid)

    Returns (extracted_text, engine_used)
    """
    if 'pdf' in mime_type:
        # Try digital extraction first
        text = _extract_digital_pdf(file_bytes)
        if len(text.strip()) > 50:
            return text, 'pymupdf'

        # Not enough text found — it's a scanned PDF
        logger.info(f"Scanned PDF detected for {s3_key}, using Textract")
        text = _extract_via_textract_s3(s3_key)
        return text, 'textract'

    elif mime_type.startswith('image/'):
        # Images always go to Textract
        # If file is over 5MB, use S3 reference instead of bytes
        if len(file_bytes) > 5 * 1024 * 1024:
            text = _extract_via_textract_s3(s3_key)
        else:
            text = _extract_via_textract_bytes(file_bytes)
        return text, 'textract'

    # Unknown type — try PyMuPDF as best effort
    text = _extract_digital_pdf(file_bytes)
    return text, 'pymupdf'


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

        if sims[best_idx] >= 0.05:
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

        if best_kat_id is None:
            tidak_ada, _ = Kategori.objects.get_or_create(
                judul='Tidak Ada',
                defaults={'deskripsi': 'Dokumen tidak dapat diklasifikasikan'}
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