(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const app          = $('app');
  const openBtn      = $('openSidebar');
  const closeBtn     = $('closeSidebar');
  const backdrop     = $('backdrop');
  const fileInput    = $('fileInput');
  const uploadZone   = $('uploadZone');
  const docList      = $('docList');
  const docCount     = $('docCount');
  const clearBtn     = $('clearBtn');
  const messagesEl   = $('messages');
  const emptyState   = $('emptyState');
  const chatArea     = $('chatArea');
  const composer     = $('composer');
  const questionInput= $('questionInput');
  const sendBtn      = $('sendBtn');
  const statusEl     = $('status');
  const dropOverlay  = $('dropOverlay');

  const state = {
    documents: [],   // { name, chunks }
    sending: false,
  };

  /* ============= Sidebar ============= */
  const SIDEBAR_KEY = 'pdfchat.sidebar';
  const isMobile = () => window.matchMedia('(max-width: 768px)').matches;

  function setSidebar(open) {
    app.classList.toggle('sidebar-closed', !open);
    openBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    try { localStorage.setItem(SIDEBAR_KEY, open ? '1' : '0'); } catch (_) {}
  }

  let savedSidebar = null;
  try { savedSidebar = localStorage.getItem(SIDEBAR_KEY); } catch (_) {}

  if (savedSidebar === '0' || (savedSidebar === null && isMobile())) {
    setSidebar(false);
  }

  openBtn.addEventListener('click',  () => setSidebar(true));
  closeBtn.addEventListener('click', () => setSidebar(false));
  backdrop.addEventListener('click', () => setSidebar(false));

  /* ============= Status ============= */
  let statusTimer;
  function setStatus(text, type = '') {
    statusEl.textContent = text || '';
    statusEl.className = 'header-status' + (type ? ' ' + type : '');
    clearTimeout(statusTimer);
    if (text) {
      statusTimer = setTimeout(() => {
        statusEl.textContent = '';
        statusEl.className = 'header-status';
      }, 4000);
    }
  }

  /* ============= Documents list ============= */
  function renderDocuments() {
    docList.innerHTML = '';
    docCount.textContent = state.documents.length;
    clearBtn.disabled = state.documents.length === 0;

    if (state.documents.length === 0) {
      const li = document.createElement('li');
      li.className = 'empty';
      li.textContent = 'No documents yet';
      docList.appendChild(li);
      return;
    }

    for (const doc of state.documents) {
      const li = document.createElement('li');
      li.className = 'doc-item';
      li.title = `${doc.name} · ${doc.chunks} chunks`;
      li.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <span class="doc-item-name"></span>
      `;
      li.querySelector('.doc-item-name').textContent = doc.name;
      docList.appendChild(li);
    }
  }

  /* ============= Upload ============= */
  async function uploadFiles(fileList) {
    const pdfs = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (!pdfs.length) {
      setStatus('Only PDF files are supported', 'error');
      return;
    }

    uploadZone.style.pointerEvents = 'none';
    uploadZone.style.opacity = '0.6';
    setStatus(`Uploading ${pdfs.length} file${pdfs.length > 1 ? 's' : ''}...`);

    let added = 0;
    for (const file of pdfs) {
      const fd = new FormData();
      fd.append('file', file);
      try {
        const res = await fetch('/api/upload', { method: 'POST', body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setStatus(data.error || `Failed to upload ${file.name}`, 'error');
          continue;
        }
        for (const r of (data.results || [])) {
          if (r.chunks !== undefined) {
            state.documents.push({ name: r.file, chunks: r.chunks });
            added++;
          } else if (r.error) {
            setStatus(`${r.file}: ${r.error}`, 'error');
          }
        }
      } catch (err) {
        setStatus(`Upload failed: ${err.message}`, 'error');
      }
    }

    uploadZone.style.pointerEvents = '';
    uploadZone.style.opacity = '';
    renderDocuments();

    if (added > 0) {
      setStatus(`Indexed ${added} file${added > 1 ? 's' : ''}`, 'success');
      if (isMobile()) setSidebar(false);
    }
  }

  uploadZone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) uploadFiles(e.target.files);
    fileInput.value = '';
  });

  /* ============= Clear all ============= */
  clearBtn.addEventListener('click', async () => {
    if (!confirm('Clear all documents and start over?')) return;
    try {
      const res = await fetch('/api/upload?reset=true', { method: 'POST' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Reset failed');
      }
      state.documents = [];
      renderDocuments();
      clearMessages();
      setStatus('All documents cleared', 'success');
    } catch (err) {
      setStatus(err.message, 'error');
    }
  });

  /* ============= Drag & drop ============= */
  let dragDepth = 0;
  window.addEventListener('dragenter', (e) => {
    if (!e.dataTransfer?.types?.includes('Files')) return;
    dragDepth++;
    dropOverlay.classList.add('active');
  });
  window.addEventListener('dragleave', () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) dropOverlay.classList.remove('active');
  });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    dragDepth = 0;
    dropOverlay.classList.remove('active');
    if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
  });

  /* ============= Chat ============= */
  function clearMessages() {
    messagesEl.innerHTML = '';
    emptyState.style.display = '';
  }

  function addMessage(role, content = '') {
    emptyState.style.display = 'none';
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.innerHTML = `
      <div class="msg-avatar">${role === 'user' ? 'You' : 'AI'}</div>
      <div class="msg-content">
        <div class="msg-role">${role === 'user' ? 'You' : 'Assistant'}</div>
        <div class="msg-body"></div>
      </div>
    `;
    const body = div.querySelector('.msg-body');
    body.textContent = content;
    messagesEl.appendChild(div);
    scrollToBottom();
    return body;
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      chatArea.scrollTop = chatArea.scrollHeight;
    });
  }

  function updateSendButton() {
    sendBtn.disabled = state.sending || !questionInput.value.trim();
  }

  async function sendQuestion(raw) {
    const question = (raw || '').trim();
    if (!question || state.sending) return;

    state.sending = true;
    updateSendButton();

    addMessage('user', question);
    questionInput.value = '';
    autoResize();

    const assistantBody = addMessage('assistant', '');
    assistantBody.classList.add('streaming');

    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `Request failed (${res.status})`);
      }

      if (!res.body) {
        assistantBody.textContent = await res.text();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let text = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        assistantBody.textContent = text;
        scrollToBottom();
      }
      text += decoder.decode();
      assistantBody.textContent = text || '(no response)';
    } catch (err) {
      assistantBody.classList.add('error');
      assistantBody.textContent = `Error: ${err.message}`;
    } finally {
      assistantBody.classList.remove('streaming');
      state.sending = false;
      updateSendButton();
      questionInput.focus();
      scrollToBottom();
    }
  }

  composer.addEventListener('submit', (e) => {
    e.preventDefault();
    sendQuestion(questionInput.value);
  });

  questionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuestion(questionInput.value);
    }
  });

  function autoResize() {
    questionInput.style.height = 'auto';
    questionInput.style.height = Math.min(questionInput.scrollHeight, 180) + 'px';
  }

  questionInput.addEventListener('input', () => {
    updateSendButton();
    autoResize();
  });

  /* ============= Init ============= */
  renderDocuments();
  autoResize();
  updateSendButton();
})();