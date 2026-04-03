/**
 * app.js — SCLU Web App
 * Handles: barcode scanning (ZXing-js), camera, file upload, manual calc, shareable URLs
 */

// ---------------------------------------------------------------------------
// ZXing lazy load
// ---------------------------------------------------------------------------
let ZXing = null;
let codeReader = null;

async function loadZXing() {
  if (ZXing) return ZXing;
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/@zxing/library@0.21.3/umd/index.min.js';
    s.onload = () => {
      ZXing = window.ZXing;
      resolve(ZXing);
    };
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

// ---------------------------------------------------------------------------
// SCLU Constants (mirrors sclu.py)
// ---------------------------------------------------------------------------
const SCLU_42_DIV = 355 * 4.2;
const SCLU_50_DIV = 355 * 5.0;

function calcSCLU(volumeMl, abv) {
  const alcoholMl = volumeMl * (abv / 100);
  const sclu42 = alcoholMl / (SCLU_42_DIV / 100);
  const sclu50 = alcoholMl / (SCLU_50_DIV / 100);
  return { sclu42: Math.round(sclu42 * 1000) / 1000, sclu50: Math.round(sclu50 * 1000) / 1000 };
}

function getCommentary(sclu) {
  if (sclu < 0.5) return "Basically water. Sip on, friend. 💧";
  if (sclu < 1.5) return "Solid. You're playing the game. 🍺";
  if (sclu < 3.0) return "Now we're cooking. Respect. 🔥";
  if (sclu < 6.0) return "This is a statement. We're impressed. 💪";
  if (sclu < 10.0) return "Sending it. Call your mom. 🚀";
  return "This is a life choice. No judgment. 💀";
}

// ---------------------------------------------------------------------------
// Result rendering
// ---------------------------------------------------------------------------
function buildResultHTML(data) {
  const volOz = (data.volume_ml / 29.5735).toFixed(1);
  const shareUrl = buildShareUrl(data);

  return `
    <div class="result-card">
      <div class="drink-name">🍺 ${data.name}</div>
      <div class="drink-meta">${data.volume_ml.toFixed(0)} ml (${volOz} oz)  ·  ${data.abv}% ABV</div>
      <div class="sclu-values">
        <div class="sclu-box">
          <div class="sclu-label">SCLU₄.₂</div>
          <div class="sclu-value">${data.sclu_42}</div>
          <div class="sclu-sub">vs standard (4.2%)</div>
        </div>
        <div class="sclu-box">
          <div class="sclu-label">SCLU₅.₀</div>
          <div class="sclu-value">${data.sclu_50}</div>
          <div class="sclu-sub">vs Banquet (5.0%)</div>
        </div>
      </div>
      <div class="commentary">${data.commentary}</div>
      ${data.source ? `<div style="text-align:center"><span class="source-badge">Source: ${data.source}</span></div>` : ''}
    </div>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="shareResult('${encodeURIComponent(shareUrl)}')">
        <span class="btn-icon">🔗</span> Share
      </button>
      <button class="btn btn-secondary" onclick="resetScan()">
        <span class="btn-icon">🔄</span> New Scan
      </button>
    </div>
  `;
}

function showResult(containerId, data) {
  const el = document.getElementById(containerId);
  el.className = '';
  el.innerHTML = buildResultHTML(data);
}

function buildShareUrl(data) {
  const params = new URLSearchParams({
    name: data.name,
    vol: data.volume_ml.toFixed(0),
    abv: data.abv,
    sclu42: data.sclu_42,
    sclu50: data.sclu_50,
  });
  return `${location.origin}${location.pathname}?${params}`;
}

function loadSharedResult(params) {
  const data = {
    name: params.get('name') || 'Unknown Drink',
    volume_ml: parseFloat(params.get('vol') || 355),
    abv: parseFloat(params.get('abv') || 4.2),
    sclu_42: parseFloat(params.get('sclu42') || 1),
    sclu_50: parseFloat(params.get('sclu50') || 0.84),
    commentary: getCommentary(parseFloat(params.get('sclu42') || 1)),
    source: 'shared link',
  };
  // Switch to manual tab and show result
  document.querySelector('[data-tab="manual"]').click();
  showResult('manualResults', data);
  // Pre-fill form
  document.getElementById('manualName').value = data.name;
}

async function shareResult(encodedUrl) {
  const url = decodeURIComponent(encodedUrl);
  if (navigator.share) {
    try {
      await navigator.share({ title: 'SCLU Result', url });
      return;
    } catch (e) { /* fall through */ }
  }
  // Fallback: copy to clipboard
  try {
    await navigator.clipboard.writeText(url);
    showStatus('scanStatus', '✅ Link copied to clipboard!', 'success');
  } catch (e) {
    prompt('Copy this link:', url);
  }
}

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------
function showStatus(id, msg, type = 'info') {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `status ${type} show`;
  el.innerHTML = msg;
}

function clearStatus(id) {
  const el = document.getElementById(id);
  if (el) el.className = 'status';
}

// ---------------------------------------------------------------------------
// Camera / scanning
// ---------------------------------------------------------------------------
let stream = null;
let scanInterval = null;

async function startCamera() {
  showStatus('scanStatus', '<span class="spinner"></span>Starting camera…', 'info');
  try {
    await loadZXing();
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }
    });

    const video = document.getElementById('video');
    video.srcObject = stream;
    await video.play();

    document.getElementById('captureOverlay').classList.add('hidden');
    document.getElementById('scanFrame').style.display = 'block';
    document.getElementById('scanLine').style.display = 'block';
    document.getElementById('btnCapture').style.display = 'flex';
    document.getElementById('btnStopCamera').style.display = 'flex';
    document.getElementById('btnCamera').style.display = 'none';

    showStatus('scanStatus', '📷 Point camera at barcode and tap Capture', 'info');

    // Also try continuous auto-scan
    startAutoScan();
  } catch (err) {
    let msg = '❌ Camera error: ' + err.message;
    if (err.name === 'NotAllowedError') msg = '❌ Camera permission denied. Please allow camera access.';
    if (err.name === 'NotFoundError') msg = '❌ No camera found. Try uploading a photo instead.';
    showStatus('scanStatus', msg, 'error');
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }
  if (scanInterval) {
    clearInterval(scanInterval);
    scanInterval = null;
  }
  const video = document.getElementById('video');
  video.srcObject = null;
  document.getElementById('captureOverlay').classList.remove('hidden');
  document.getElementById('scanFrame').style.display = 'none';
  document.getElementById('scanLine').style.display = 'none';
  document.getElementById('btnCapture').style.display = 'none';
  document.getElementById('btnStopCamera').style.display = 'none';
  document.getElementById('btnCamera').style.display = 'flex';
  clearStatus('scanStatus');
}

function startAutoScan() {
  if (scanInterval) clearInterval(scanInterval);
  scanInterval = setInterval(async () => {
    if (!stream) { clearInterval(scanInterval); return; }
    try {
      const barcode = await grabFrameAndDecode();
      if (barcode) {
        clearInterval(scanInterval);
        await lookupBarcode(barcode);
      }
    } catch (e) { /* keep trying */ }
  }, 800);
}

async function captureFrame() {
  showStatus('scanStatus', '<span class="spinner"></span>Scanning…', 'info');
  try {
    const barcode = await grabFrameAndDecode();
    if (barcode) {
      await lookupBarcode(barcode);
    } else {
      // Fall back to server-side
      const blob = await grabFrameAsBlob();
      await sendImageToServer(blob, 'scanResults', 'scanStatus');
    }
  } catch (err) {
    showStatus('scanStatus', '❌ Scan failed: ' + err.message, 'error');
  }
}

async function grabFrameAndDecode() {
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0);

  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

  if (!ZXing) await loadZXing();
  const hints = new Map();
  const formats = [
    ZXing.BarcodeFormat.EAN_13,
    ZXing.BarcodeFormat.EAN_8,
    ZXing.BarcodeFormat.UPC_A,
    ZXing.BarcodeFormat.UPC_E,
    ZXing.BarcodeFormat.CODE_128,
  ];
  hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, formats);

  const reader = new ZXing.MultiFormatReader();
  reader.setHints(hints);
  const luminance = new ZXing.RGBLuminanceSource(imageData.data, canvas.width, canvas.height);
  const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(luminance));
  const result = reader.decode(bitmap);
  return result.getText();
}

async function grabFrameAsBlob() {
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
}

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------
async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  showStatus('scanStatus', '<span class="spinner"></span>Reading image…', 'info');

  // Show preview
  const url = URL.createObjectURL(file);
  const overlay = document.getElementById('captureOverlay');
  overlay.innerHTML = `<img src="${url}" style="max-width:100%;max-height:100%;object-fit:contain">`;
  overlay.classList.remove('hidden');

  // Try client-side barcode first
  try {
    const barcode = await decodeImageFile(file);
    if (barcode) {
      await lookupBarcode(barcode);
      return;
    }
  } catch (e) { /* fall through to server */ }

  // Server-side fallback
  await sendImageToServer(file, 'scanResults', 'scanStatus');
}

async function decodeImageFile(file) {
  if (!ZXing) await loadZXing();
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);

      try {
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const hints = new Map();
        hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
          ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8,
          ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E,
          ZXing.BarcodeFormat.CODE_128,
        ]);
        hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
        const reader = new ZXing.MultiFormatReader();
        reader.setHints(hints);
        const luminance = new ZXing.RGBLuminanceSource(imageData.data, canvas.width, canvas.height);
        const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(luminance));
        const result = reader.decode(bitmap);
        resolve(result.getText());
      } catch (e) {
        resolve(null);
      }
    };
    img.onerror = () => reject(new Error('Failed to load image'));
    img.src = url;
  });
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------
async function lookupBarcode(barcode) {
  showStatus('scanStatus', `<span class="spinner"></span>Found barcode: ${barcode} — looking up…`, 'info');
  stopCamera();

  try {
    const resp = await fetch(`/api/sclu/barcode?code=${encodeURIComponent(barcode)}`);
    if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
    const data = await resp.json();
    clearStatus('scanStatus');
    showResult('scanResults', data);
  } catch (err) {
    showStatus('scanStatus', `❌ Lookup failed: ${err.message}`, 'error');
  }
}

async function sendImageToServer(file, resultsId, statusId) {
  showStatus(statusId, '<span class="spinner"></span>Sending to server for analysis…', 'info');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch('/api/sclu/image', { method: 'POST', body: formData });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    clearStatus(statusId);
    showResult(resultsId, data);
  } catch (err) {
    showStatus(statusId, `❌ Server error: ${err.message}. Try manual entry instead.`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Manual calculation (pure JS, no backend needed)
// ---------------------------------------------------------------------------
let volumeUnit = 'oz';

function setVolumeUnit(unit) {
  volumeUnit = unit;
  document.querySelectorAll('.unit-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.unit === unit);
  });
}

function toMl(value, unit) {
  switch (unit) {
    case 'oz': return value * 29.5735;
    case 'L':  return value * 1000;
    default:   return value; // ml
  }
}

function calculateManual() {
  const name = document.getElementById('manualName').value.trim() || 'Unknown Drink';
  const volRaw = parseFloat(document.getElementById('manualVolume').value);
  const abv = parseFloat(document.getElementById('manualAbv').value);

  if (!volRaw || volRaw <= 0) {
    alert('Please enter a valid volume.');
    return;
  }
  if (!abv || abv < 0 || abv > 100) {
    alert('Please enter a valid ABV (0–100).');
    return;
  }

  const volumeMl = toMl(volRaw, volumeUnit);
  const { sclu42, sclu50 } = calcSCLU(volumeMl, abv);

  const data = {
    name,
    volume_ml: volumeMl,
    abv,
    sclu_42: sclu42,
    sclu_50: sclu50,
    commentary: getCommentary(sclu42),
    source: 'manual',
  };

  showResult('manualResults', data);

  // Update URL for sharing (no page reload)
  const shareUrl = buildShareUrl(data);
  history.replaceState(null, '', shareUrl);
}

function resetScan() {
  document.getElementById('scanResults').className = 'results-hidden';
  document.getElementById('scanResults').innerHTML = '';
  clearStatus('scanStatus');
  document.getElementById('captureOverlay').classList.remove('hidden');
  document.getElementById('captureOverlay').innerHTML = `
    <span style="font-size:3rem">📸</span>
    <span style="color:rgba(255,255,255,0.8); font-size:0.9rem">Start camera or upload photo</span>
  `;
}
