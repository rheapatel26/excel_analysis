/**
 * ppt-builder.js
 * Core logic for Excel parsing, NLP chart generation, drag-drop canvas, and PPTX export.
 */

let rowData = [];
let headers = [];
let slideElements = [];
let currentTemplate = 'corporate';
let geminiKey = localStorage.getItem('gemini_api_key') || '';

const templates = {
  corporate: { bg: '#ffffff', accent: '#1e293b', text: '#334155' },
  dark: { bg: '#0f172a', accent: '#6366f1', text: '#f1f5f9' },
  minimal: { bg: '#f8fafc', accent: '#000000', text: '#334155' },
  gradient: { bg: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', accent: '#ffffff', text: '#ffffff' },
  neon: { bg: '#000000', accent: '#00ff00', text: '#ffffff' }
};

/* ── Init interact.js ──────────────────────────── */
function initDragDrop() {
  interact('.draggable')
    .draggable({
      inertia: true,
      modifiers: [
        interact.modifiers.restrictRect({
          restriction: '#slide-canvas',
          endOnly: true
        })
      ],
      autoScroll: true,
      listeners: {
        move: dragMoveListener,
      }
    })
    .resizable({
      edges: { left: true, right: true, bottom: true, top: true },
      listeners: {
        move: resizeMoveListener
      }
    });
}

function dragMoveListener(event) {
  var target = event.target;
  var x = (parseFloat(target.getAttribute('data-x')) || 0) + event.dx;
  var y = (parseFloat(target.getAttribute('data-y')) || 0) + event.dy;

  target.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
  target.setAttribute('data-x', x);
  target.setAttribute('data-y', y);
}

function resizeMoveListener(event) {
  var target = event.target;
  var x = (parseFloat(target.getAttribute('data-x')) || 0);
  var y = (parseFloat(target.getAttribute('data-y')) || 0);

  target.style.width = event.rect.width + 'px';
  target.style.height = event.rect.height + 'px';

  x += event.deltaRect.left;
  y += event.deltaRect.top;

  target.style.transform = 'translate(' + x + 'px,' + y + 'px)';
  target.setAttribute('data-x', x);
  target.setAttribute('data-y', y);
}

/* ── Excel Parser ──────────────────────────────── */
function handleFileUpload(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const data = new Uint8Array(e.target.result);
    const workbook = XLSX.read(data, { type: 'array' });
    const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
    rowData = XLSX.utils.sheet_to_json(firstSheet);
    headers = Object.keys(rowData[0] || {});
    
    document.getElementById('data-status').innerHTML = `✅ ${file.name} loaded (${rowData.length} rows)`;
    showToast('Data loaded successfully!', 'success');
  };
  reader.readAsArrayBuffer(file);
}

/* ── Chart Generation ──────────────────────────── */
async function generateChartFromQuery() {
  const query = document.getElementById('chart-query').value;
  if (!query || !rowData.length) return;

  setLoading(true);
  try {
    // 1. Ask Gemini to map query to columns and chart type
    const prompt = `Analyze this Excel data structure: Columns: [${headers.join(', ')}]. 
    User query: "${query}". 
    Choose the best chart type (bar, line, pie, scatter) and identify the X-axis and Y-axis columns.
    Return ONLY JSON: {"type": "bar", "x": "column_name", "y": "column_name", "title": "Chart Title"}`;

    const response = await callGemini(prompt);
    const config = JSON.parse(response.replace(/```json|```/g, '').trim());

    // 2. Process data for chart
    const labels = rowData.slice(0, 15).map(r => r[config.x]);
    const values = rowData.slice(0, 15).map(r => r[config.y]);

    // 3. Create Chart.js instance in gallery
    const canvas = document.createElement('canvas');
    canvas.width = 300;
    canvas.height = 200;
    
    new Chart(canvas, {
      type: config.type,
      data: {
        labels: labels,
        datasets: [{
          label: config.title,
          data: values,
          backgroundColor: 'rgba(99, 102, 241, 0.5)',
          borderColor: 'rgb(99, 102, 241)',
          borderWidth: 1
        }]
      },
      options: { responsive: false }
    });

    const gallery = document.getElementById('chart-gallery');
    const item = document.createElement('div');
    item.className = 'chart-item';
    item.appendChild(canvas);
    item.onclick = () => addToSlide(canvas.toDataURL(), 'chart');
    gallery.prepend(item);

  } catch (err) {
    console.error(err);
    showToast('Failed to generate chart', 'error');
  } finally {
    setLoading(false);
  }
}

/* ── Canvas Logic ──────────────────────────────── */
function addToSlide(content, type) {
  const canvas = document.getElementById('slide-canvas');
  const el = document.createElement('div');
  el.className = 'draggable';
  el.style.width = type === 'chart' ? '400px' : '200px';
  el.style.height = type === 'chart' ? '300px' : '100px';
  el.setAttribute('data-type', type);

  if (type === 'chart' || type === 'image') {
    const img = new Image();
    img.src = content;
    el.appendChild(img);
  } else {
    el.innerText = content;
    el.style.color = templates[currentTemplate].text;
    el.contentEditable = true;
  }

  canvas.appendChild(el);
  initDragDrop();
}

function selectTemplate(name) {
  currentTemplate = name;
  const canvas = document.getElementById('slide-canvas');
  const t = templates[name];
  canvas.style.background = t.bg;
  
  // Update all text elements
  document.querySelectorAll('.draggable[data-type="text"]').forEach(el => {
    el.style.color = t.text;
  });
}

/* ── PPT Export ────────────────────────────────── */
async function exportToPPT() {
  const pptx = new PptxGenJS();
  const slide = pptx.addSlide();
  
  const canvas = document.getElementById('slide-canvas');
  const rect = canvas.getBoundingClientRect();
  const ratio = 10 / rect.width; // PptxGenJS uses inches (10x5.625 for 16:9)

  // Background
  const t = templates[currentTemplate];
  if (t.bg.startsWith('linear')) {
    slide.background = { color: '333333' }; // Gradient support is complex, use dark fallback
  } else {
    slide.background = { color: t.bg.replace('#', '') };
  }

  // Elements
  const elements = document.querySelectorAll('.draggable');
  elements.forEach(el => {
    const type = el.getAttribute('data-type');
    const x = (parseFloat(el.getAttribute('data-x')) || 0) + el.offsetLeft;
    const y = (parseFloat(el.getAttribute('data-y')) || 0) + el.offsetTop;
    const w = el.offsetWidth;
    const h = el.offsetHeight;

    const opts = {
      x: (x / rect.width) * 10,
      y: (y / rect.height) * 5.625,
      w: (w / rect.width) * 10,
      h: (h / rect.height) * 5.625
    };

    if (type === 'chart' || type === 'image') {
      slide.addImage({ data: el.querySelector('img').src, ...opts });
    } else {
      slide.addText(el.innerText, { ...opts, color: t.text.replace('#', ''), fontSize: 18 });
    }
  });

  pptx.writeFile({ fileName: `Analysis_Report_${Date.now()}.pptx` });
}

/* ── Gemini Helper ─────────────────────────────── */
async function callGemini(prompt) {
  if (!geminiKey) {
    geminiKey = prompt('Please enter your Google Gemini API Key:');
    if (geminiKey) localStorage.setItem('gemini_api_key', geminiKey);
  }
  
  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${geminiKey}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
  });
  const data = await response.json();
  return data.candidates[0].content.parts[0].text;
}

/* ── AI Chat ───────────────────────────────────── */
async function sendChat() {
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query) return;

  appendMessage('user', query);
  input.value = '';

  try {
    const prompt = `Context: We are analyzing an Excel file with ${rowData.length} rows. 
    Columns: [${headers.join(', ')}]. 
    Task: ${query}`;
    
    const response = await callGemini(prompt);
    appendMessage('ai', response);
  } catch (err) {
    appendMessage('ai', 'Error: ' + err.message);
  }
}

function appendMessage(role, text) {
  const container = document.getElementById('chat-messages');
  const msg = document.createElement('div');
  msg.className = `msg msg-${role}`;
  msg.innerText = text;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

function setLoading(val) {
  document.getElementById('loading').style.display = val ? 'flex' : 'none';
}

function showToast(msg, type) {
  // Simple toast using existing style or alert
  const toast = document.createElement('div');
  toast.style.position = 'fixed';
  toast.style.bottom = '20px';
  toast.style.left = '50%';
  toast.style.transform = 'translateX(-50%)';
  toast.style.background = type === 'success' ? '#10b981' : '#f43f5e';
  toast.style.color = 'white';
  toast.style.padding = '10px 20px';
  toast.style.borderRadius = '8px';
  toast.style.zIndex = '1000';
  toast.innerText = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

/* ── UI Triggers ───────────────────────────────── */
window.onload = () => {
  initDragDrop();
  
  document.getElementById('file-input').onchange = (e) => {
    if (e.target.files.length) handleFileUpload(e.target.files[0]);
  };

  // Sync key from main dashboard if possible
  if (!geminiKey) {
    geminiKey = localStorage.getItem('gemini_api_key');
  }
};
