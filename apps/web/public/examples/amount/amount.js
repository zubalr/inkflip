/**
 * Browser Amount Demo client script (T17).
 *
 * Implements interactive browser rendering via PDF.js, pixel equality assertion
 * with the clean counterpart control, and live file validation.
 */
import * as pdfjs from '/node_modules/pdfjs-dist/legacy/build/pdf.mjs';

// Configure pinned worker
pdfjs.GlobalWorkerOptions.workerSrc = '/node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs';

const MAPPING_AMOUNT_HASH = '04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80';
const MAPPING_CONTROL_HASH = '19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed';

async function computeSha256(arrayBuffer) {
  const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function renderPdfToCanvas(urlOrData, canvas) {
  const loadingTask = pdfjs.getDocument({
    ...(typeof urlOrData === 'string' ? { url: urlOrData } : { data: urlOrData }),
    workerSrc: '/node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs',
    cMapUrl: '/assets/pdfjs/6.3.289/cmaps/',
    cMapPacked: true,
    standardFontDataUrl: '/assets/pdfjs/6.3.289/standard_fonts/',
    wasmUrl: '/assets/pdfjs/6.3.289/wasm/',
    iccUrl: '/assets/pdfjs/6.3.289/iccs/',
    isEvalSupported: false,
    disableFontFace: false,
  });

  const doc = await loadingTask.promise;
  const page = await doc.getPage(1);
  const viewport = page.getViewport({ scale: 2.0 });
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  await page.render({ canvasContext: ctx, viewport }).promise;

  const textContent = await page.getTextContent();
  const textItems = textContent.items
    .filter(item => 'str' in item && item.str)
    .map(item => item.str);

  return { doc, page, textItems, ctx };
}

// Initial render of source demo
async function initDemo() {
  const sourceCanvas = document.getElementById('rendered-amount-canvas');
  try {
    const res = await renderPdfToCanvas('/examples/amount/mapping-amount.pdf', sourceCanvas);
    window.__sourceRenderResult = res;
  } catch (err) {
    console.error('Failed initial render:', err);
  }
}

// Control comparison logic (criterion 6)
async function compareWithControl() {
  const statusEl = document.getElementById('pixel-match-status');
  const controlCanvas = document.getElementById('control-rendered-canvas');
  statusEl.textContent = 'Rendering control and comparing pixels...';

  try {
    const t0 = performance.now();
    const controlRes = await renderPdfToCanvas('/examples/amount/mapping-control.pdf', controlCanvas);
    const sourceCanvas = document.getElementById('rendered-amount-canvas');

    const ctxSource = sourceCanvas.getContext('2d', { willReadFrequently: true });
    const ctxControl = controlCanvas.getContext('2d', { willReadFrequently: true });

    const imgSource = ctxSource.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height);
    const imgControl = ctxControl.getImageData(0, 0, controlCanvas.width, controlCanvas.height);

    let diffCount = 0;
    const totalPixels = imgSource.data.length / 4;
    for (let i = 0; i < imgSource.data.length; i += 4) {
      if (
        imgSource.data[i] !== imgControl.data[i] ||
        imgSource.data[i + 1] !== imgControl.data[i + 1] ||
        imgSource.data[i + 2] !== imgControl.data[i + 2] ||
        imgSource.data[i + 3] !== imgControl.data[i + 3]
      ) {
        diffCount++;
      }
    }

    const elapsed = Math.round(performance.now() - t0);
    window.__controlComparison = {
      diffCount,
      totalPixels,
      elapsed,
      controlText: controlRes.textItems,
    };

    if (diffCount === 0) {
      statusEl.textContent = `100% pixel match — 0 differing pixels (verified in ${elapsed} ms)`;
      statusEl.style.color = 'var(--color-teal)';
    } else {
      statusEl.textContent = `Differences detected: ${diffCount} pixels differ`;
      statusEl.style.color = 'var(--color-rust)';
    }
  } catch (err) {
    statusEl.textContent = 'Comparison failed: ' + err.message;
    statusEl.style.color = 'var(--color-rust)';
  }
}

// Live file intake (criteria 1, 2, 3, 5)
async function handleFileIntake(file) {
  if (!file) return;

  const tStart = performance.now();
  const container = document.getElementById('live-result-container');
  const nameEl = document.getElementById('live-file-name');
  const hashEl = document.getElementById('live-file-hash');
  const textEl = document.getElementById('live-extracted-text');
  const noticeEl = document.getElementById('replay-notice');
  const badgeEl = document.getElementById('provenance-badge');
  const timingEl = document.getElementById('timing-display');

  container.style.display = 'block';
  container.setAttribute('data-state', 'processing');
  nameEl.textContent = file.name;
  textEl.textContent = 'Extracting...';

  const buf = await file.arrayBuffer();
  const hash = await computeSha256(buf);
  hashEl.textContent = hash;

  // Criterion 2: modified bytes cannot replay old prepared result
  if (hash === MAPPING_AMOUNT_HASH) {
    // Identical bytes (even if renamed): criterion 1
    noticeEl.className = 'notice-box';
    noticeEl.textContent = 'Byte-identical to mapping-amount.pdf fixture. Executing live reader extraction.';
  } else if (hash === MAPPING_CONTROL_HASH) {
    noticeEl.className = 'notice-box';
    noticeEl.textContent = 'Byte-identical to mapping-control.pdf fixture. Executing live reader extraction.';
  } else {
    // Modified bytes!
    noticeEl.className = 'notice-box tamper-warning';
    noticeEl.textContent = 'Modified bytes detected: hash does not match prepared manifest. Prepared report replay rejected. Executed live.';
  }

  // Live reader extraction (no canned data)
  try {
    const loadingTask = pdfjs.getDocument({
      data: new Uint8Array(buf),
      workerSrc: '/node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs',
      cMapUrl: '/assets/pdfjs/6.3.289/cmaps/',
      cMapPacked: true,
      standardFontDataUrl: '/assets/pdfjs/6.3.289/standard_fonts/',
      wasmUrl: '/assets/pdfjs/6.3.289/wasm/',
      iccUrl: '/assets/pdfjs/6.3.289/iccs/',
      isEvalSupported: false,
      disableFontFace: false,
    });
    const doc = await loadingTask.promise;
    const page = await doc.getPage(1);
    const content = await page.getTextContent();
    const items = content.items
      .filter(i => 'str' in i && i.str)
      .map(i => i.str);

    textEl.textContent = items.join(' ');

    const elapsed = Math.round(performance.now() - tStart);
    timingEl.textContent = `${elapsed} ms`;

    // Criterion 3: live provenance label
    badgeEl.textContent = 'live';
    badgeEl.className = 'badge badge-live';
    badgeEl.setAttribute('data-provenance', 'live');
    container.setAttribute('data-state', 'complete');

    window.__lastLiveResult = {
      filename: file.name,
      hash,
      items,
      elapsed,
      provenance: 'live',
      replayedPrepared: false,
    };
  } catch (err) {
    textEl.textContent = 'Error extracting text: ' + err.message;
    container.setAttribute('data-state', 'error');
    window.__lastLiveResult = {
      filename: file.name,
      hash,
      items: [],
      elapsed: Math.round(performance.now() - tStart),
      provenance: 'live',
      replayedPrepared: false,
      error: err.message,
    };
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initDemo();

  const compareBtn = document.getElementById('btn-compare-control');
  if (compareBtn) {
    compareBtn.addEventListener('click', compareWithControl);
  }

  const fileInput = document.getElementById('file-input');
  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files?.[0];
      if (file) handleFileIntake(file);
    });
  }
});
