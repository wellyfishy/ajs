/**
 * DokumenProgress — persistent upload/OCR progress panel.
 * Renders bottom-right on every page.
 * Survives logout: uses localStorage to remember pending IDs,
 * polls the public /api/dokumen/<id>/progress/ endpoint.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'dokumen_pending_ids';
  const POLL_MS     = 3000;

  // { [dokumen_id]: { nama_file, upload_status, upload_progress,
  //                   ocr_status, ocr_progress, kategori } }
  let state     = {};
  let pollTimer = null;
  let panelEl   = null;

  // ── Init ────────────────────────────────────────────────────
  function init() {
    buildPanel();
    restoreFromStorage();
    if (hasPending()) startPolling();
  }

  // ── Public API ──────────────────────────────────────────────
  window.DokumenProgress = {
    track(dokumenId, namaFile) {
      state[String(dokumenId)] = {
        nama_file:        namaFile,
        upload_status:    'pending',
        upload_progress:  0,
        ocr_status:       'pending',
        ocr_progress:     0,
        kategori:         null,
      };
      saveToStorage();
      renderPanel();
      startPolling();
    }
  };

  // ── Storage ─────────────────────────────────────────────────
  function saveToStorage() {
    const pending = Object.keys(state).filter(id => !isDone(state[id]));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pending));
  }

  function restoreFromStorage() {
    try {
      const ids = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      ids.forEach(id => {
        if (!state[id]) {
          state[String(id)] = {
            nama_file:       `Dokumen #${id}`,
            upload_status:   'pending',
            upload_progress: 0,
            ocr_status:      'pending',
            ocr_progress:    0,
            kategori:        null,
          };
        }
      });
    } catch (_) {}
  }

  // ── Polling ─────────────────────────────────────────────────
  function hasPending() {
    return Object.keys(state).some(id => !isDone(state[id]));
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollAll, POLL_MS);
  }

  async function pollAll() {
    const pending = Object.keys(state).filter(id => !isDone(state[id]));
    if (!pending.length) {
      clearInterval(pollTimer);
      pollTimer = null;
      return;
    }
    await Promise.all(pending.map(pollOne));
    renderPanel();
    saveToStorage();
  }

  async function pollOne(id) {
    try {
      const res  = await fetch(`/api/dokumen/${id}/progress/`);
      if (!res.ok) return;
      const data = await res.json();
      state[String(id)] = {
        nama_file:       data.nama_file       || state[id].nama_file,
        upload_status:   data.upload_status,
        upload_progress: data.upload_progress,
        ocr_status:      data.ocr_status,
        ocr_progress:    data.ocr_progress,
        kategori:        data.kategori,
      };
    } catch (_) { /* network error — keep existing state */ }
  }

  function isDone(s) {
    const uploadDone = s.upload_status === 'uploaded' || s.upload_status === 'failed';
    const ocrDone    = s.ocr_status    === 'done'     || s.ocr_status    === 'failed';
    return uploadDone && ocrDone;
  }

  // ── UI ───────────────────────────────────────────────────────
  function buildPanel() {
    panelEl = document.createElement('div');
    panelEl.id = 'dokumenProgressPanel';
    Object.assign(panelEl.style, {
      position:   'fixed',
      bottom:     '20px',
      right:      '20px',
      zIndex:     '9999',
      width:      '320px',
      maxHeight:  '440px',
      overflowY:  'auto',
      background: '#131225',
      borderRadius: '10px',
      boxShadow:  '0 4px 24px rgba(0,0,0,0.15)',
      fontSize:   '13px',
      display:    'none',
      fontFamily: 'system-ui, sans-serif',
    });
    document.body.appendChild(panelEl);
  }

  function renderPanel() {
    const ids = Object.keys(state);
    if (!ids.length) {
      panelEl.style.display = 'none';
      return;
    }
    panelEl.style.display = 'block';

    const rows = ids.map(id => {
      const s       = state[id];
      const pct     = overallProgress(s);
      const label   = overallLabel(s);
      const done    = isDone(s);
      const barColor = s.upload_status === 'failed' || s.ocr_status === 'failed'
        ? '#dc3545' : done ? '#198754' : '#0d6efd';

      return `
        <div style="padding:10px 14px;border-bottom:1px solid #f0f0f0;">
          <div style="display:flex;justify-content:space-between;
                      align-items:center;margin-bottom:5px;">
            <span style="font-weight:600;overflow:hidden;white-space:nowrap;
                         text-overflow:ellipsis;max-width:195px;"
                  title="${esc(s.nama_file)}">${esc(s.nama_file)}</span>
            <span style="font-size:11px;color:${done ? '#198754' : '#6c757d'};
                         white-space:nowrap;margin-left:6px;">${label}</span>
          </div>
          <div style="background:#e9ecef;border-radius:4px;height:5px;">
            <div style="background:${barColor};width:${pct}%;height:100%;
                        border-radius:4px;transition:width .4s;"></div>
          </div>
          ${s.kategori
            ? `<small style="color:#6c757d;margin-top:3px;display:block;">
                 📂 ${esc(s.kategori)}</small>`
            : ''}
        </div>`;
    });

    panelEl.innerHTML = `
      <div style="padding:10px 14px;background:#131225;
                  border-radius:10px 10px 0 0;
                  display:flex;justify-content:space-between;align-items:center;
                  position:sticky;top:0;">
        <span style="font-weight:700;font-size:13px;">📤 Dokumen Pipeline</span>
        <button onclick="this.closest('#dokumenProgressPanel').style.display='none'"
                style="background:none;border:none;cursor:pointer;
                       font-size:18px;line-height:1;color:#6c757d;">×</button>
      </div>
      ${rows.join('')}
    `;
  }

  function overallProgress(s) {
    if (s.upload_status === 'failed') return 100;
    if (s.upload_status === 'pending')   return 0;
    if (s.upload_status === 'uploading') return Math.round(s.upload_progress * 0.5);
    // uploaded — now in OCR phase (50–100%)
    if (s.ocr_status === 'pending')    return 50;
    if (s.ocr_status === 'processing') return 50 + Math.round(s.ocr_progress * 0.5);
    return 100;
  }

  function overallLabel(s) {
    if (s.upload_status === 'pending')    return '⏳ Antri...';
    if (s.upload_status === 'uploading')  return `⬆ Upload ${s.upload_progress}%`;
    if (s.upload_status === 'failed')     return '✗ Upload gagal';
    if (s.ocr_status    === 'pending')    return '⏳ Menunggu OCR...';
    if (s.ocr_status    === 'processing') return `🔍 OCR ${s.ocr_progress}%`;
    if (s.ocr_status    === 'failed')     return '✗ OCR gagal';
    if (s.ocr_status    === 'done')       return '✓ Selesai';
    return '...';
  }

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  document.addEventListener('DOMContentLoaded', init);
})();