// Main dashboard logic (no deps)
(function(){
  const { State, savePinned, saveTemplates, saveAutoChain, statusIsActive, partitionRuns } = window.AppState;
  const API = window.DashboardAPI;

  // Elements
  const activeCountEl = document.getElementById('activeCount');
  const activeHeader = document.getElementById('activeRunsHeader');
  const activeDropdown = document.getElementById('activeDropdown');
  const activeListEl = document.getElementById('activeList');
  const runsListEl = document.getElementById('runsList');
  const viewSelect = document.getElementById('viewSelect');
  const createBtn = document.getElementById('createRunBtn');
  const promptInput = document.getElementById('newRunPrompt');
  const modelSelect = document.getElementById('modelSelect');
  const repoIdInput = document.getElementById('newRunRepoId');
  const logsContainer = document.getElementById('logsContainer');
  const logsRunId = document.getElementById('logsRunId');
  const pauseLogsBtn = document.getElementById('pauseLogsBtn');
  const copyLogsBtn = document.getElementById('copyLogsBtn');

  const tabs = document.querySelectorAll('.tab-button');
  const tabRuns = document.getElementById('tab-runs');
  const tabTemplates = document.getElementById('tab-templates');

  const tplName = document.getElementById('tplName');
  const tplText = document.getElementById('tplText');
  const addTemplateBtn = document.getElementById('addTemplateBtn');
  const exportTemplatesBtn = document.getElementById('exportTemplatesBtn');
  const importTemplatesBtn = document.getElementById('importTemplatesBtn');
  const templatesList = document.getElementById('templatesList');

  // Notifications (system)
  let notifEnabled = false;
  try {
    if ('Notification' in window) {
      if (Notification.permission === 'granted') notifEnabled = true;
      else if (Notification.permission !== 'denied') {
        Notification.requestPermission().then((p) => { if (p === 'granted') notifEnabled = true; });
      }
    }
  } catch {}
  function notify(title, body) {
    try { if (notifEnabled) new Notification(title, { body }); } catch {}
  }

  // Header hover behavior
  let hoverTimer = null;
  activeHeader.addEventListener('mouseenter', () => {
    clearTimeout(hoverTimer);
    activeDropdown.hidden = false;
  });
  activeHeader.addEventListener('mouseleave', () => {
    hoverTimer = setTimeout(() => { activeDropdown.hidden = true; }, 250);
  });

  // Tabs
  tabs.forEach((btn) => {
    btn.addEventListener('click', () => {
      tabs.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.getAttribute('data-tab');
      if (tab === 'runs') {
        tabRuns.classList.remove('hidden');
        tabTemplates.classList.add('hidden');
      } else {
        tabTemplates.classList.remove('hidden');
        tabRuns.classList.add('hidden');
      }
    });
  });

  // Filter (compact)
  if (viewSelect) viewSelect.addEventListener('change', renderRuns);

  // Create run
  createBtn.addEventListener('click', async () => {
    const prompt = promptInput.value.trim();
    const model = modelSelect.value;
    const repo_id = Number(repoIdInput.value) || undefined;
    if (!prompt) { Toast.show('Enter a prompt'); return; }
    try {
      const res = await API.createRun({ prompt, model, repo_id });
      Toast.show(`Created run #${res.id}`);
      promptInput.value = '';
      // Refresh immediately
      await refreshRuns();
    } catch (e) {
      console.error(e);
      Toast.show('Failed to create run');
    }
  });

  // Templates CRUD
  function renderTemplates() {
    templatesList.innerHTML = '';
    State.templates.forEach((t, idx) => {
      const row = document.createElement('div');
      row.className = 'run-card';
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = t.name || `(template ${idx+1})`;
      const text = document.createElement('pre');
      text.textContent = t.text || '';
      const actions = document.createElement('div');
      actions.className = 'actions';
      const editBtn = document.createElement('button'); editBtn.textContent = 'Edit';
      const delBtn = document.createElement('button'); delBtn.textContent = 'Delete';
      actions.appendChild(editBtn); actions.appendChild(delBtn);
      row.appendChild(meta); row.appendChild(text); row.appendChild(actions);
      templatesList.appendChild(row);

      editBtn.addEventListener('click', () => {
        tplName.value = t.name || '';
        tplText.value = t.text || '';
      });
      delBtn.addEventListener('click', () => {
        State.templates.splice(idx,1);
        saveTemplates();
        renderTemplates();
      });
    });
  }

  addTemplateBtn.addEventListener('click', () => {
    const name = tplName.value.trim();
    const text = tplText.value.trim();
    if (!name || !text) { Toast.show('Enter name and text'); return; }
    const existing = State.templates.find((t) => t.name === name);
    if (existing) { existing.text = text; }
    else State.templates.push({ name, text });
    saveTemplates();
    tplName.value=''; tplText.value='';
    renderTemplates();
  });

  exportTemplatesBtn.addEventListener('click', () => {
    const data = JSON.stringify(State.templates, null, 2);
    navigator.clipboard.writeText(data).then(() => Toast.show('Templates copied to clipboard'));
  });

  importTemplatesBtn.addEventListener('click', async () => {
    const json = prompt('Paste templates JSON');
    if (!json) return;
    try {
      const arr = JSON.parse(json);
      if (!Array.isArray(arr)) throw new Error('Invalid');
      State.templates = arr;
      saveTemplates();
      renderTemplates();
    } catch {
      Toast.show('Invalid JSON');
    }
  });

  // Rendering runs
  function renderActiveHeader() {
    activeCountEl.textContent = String(State.active.length);
    activeListEl.innerHTML = '';
    State.active.slice(0, 50).forEach((r) => {
      const row = document.createElement('div');
      row.className = 'run-card';
      row.style.padding = '6px';
      row.innerHTML = `#${r.id} <span class="status active">${r.status || ''}</span>`;
      row.addEventListener('click', () => openLogs(r.id));
      activeListEl.appendChild(row);
    });
  }

  function runCard(r) {
    const el = document.createElement('div');
    el.className = 'run-card';

    // Header row
    const title = document.createElement('div');
    title.textContent = `#${r.id}`;
    const meta = document.createElement('div');
    meta.className = 'meta';
    const d = new Date(r.created_at || Date.now());
    const statusCls = statusIsActive(r.status) ? 'active' : 'past';
    meta.innerHTML = `<span class=\"status ${statusCls}\">${r.status || ''}</span> <span>${d.toLocaleString()}</span>`;

    const actions = document.createElement('div');
    actions.className = 'actions';
    const openBtn = document.createElement('button'); openBtn.textContent = 'Logs'; openBtn.className='icon-btn';
    const pinBtn = document.createElement('button'); pinBtn.textContent = State.pinned.has(r.id) ? 'Unpin' : 'Pin'; pinBtn.className='icon-btn';
    const watchBtn = document.createElement('button'); watchBtn.textContent = State.watchers.has(r.id) ? 'Unwatch' : 'Watch'; watchBtn.className='icon-btn';
    actions.appendChild(openBtn);
    actions.appendChild(pinBtn);
    actions.appendChild(watchBtn);

    const quick = document.createElement('div');
    quick.className = 'quick';

    if (statusIsActive(r.status)) {
      const chainSel = document.createElement('select'); chainSel.multiple = true; chainSel.size = 3; chainSel.style.minWidth = '160px';
      State.templates.forEach((t) => { const o = document.createElement('option'); o.value=t.name; o.textContent=t.name; chainSel.appendChild(o); });
      const applyChainBtn = document.createElement('button'); applyChainBtn.textContent = 'Add Chains'; applyChainBtn.className='icon-btn';
      quick.appendChild(chainSel);
      quick.appendChild(applyChainBtn);
      applyChainBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const selected = Array.from(chainSel.selectedOptions).map((o) => o.value).filter(Boolean);
        if (selected.length === 0) { Toast.show('Select templates'); return; }
        const plan = selected.map((nm) => ({ name: nm }));
        r.__chainPlan = plan; r.__chainIndex = 0; r.__lastState = r.status || '';
        Toast.show(`Chaining set on #${r.id}: ${selected.join(' -> ')}`);
        ensureWatch(r.id);
      });
    } else {
      const resumeRow = document.createElement('div'); resumeRow.className='actions';
      const resumeSel = document.createElement('select');
      const emptyOpt = document.createElement('option'); emptyOpt.value=''; emptyOpt.textContent = '(choose template)'; resumeSel.appendChild(emptyOpt);
      State.templates.forEach((t) => { const o = document.createElement('option'); o.value=t.name; o.textContent=t.name; resumeSel.appendChild(o); });
      const resumeBtn = document.createElement('button'); resumeBtn.textContent = 'Resume'; resumeBtn.className='icon-btn';
      const adhoc = document.createElement('input'); adhoc.placeholder='Ad-hoc prompt'; adhoc.className='small-input';
      const adhocBtn = document.createElement('button'); adhocBtn.textContent = 'Send'; adhocBtn.className='icon-btn';
      resumeRow.appendChild(resumeSel);
      resumeRow.appendChild(resumeBtn);
      quick.appendChild(resumeRow);
      quick.appendChild(adhoc);
      quick.appendChild(adhocBtn);
      resumeBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const name = resumeSel.value;
        if (!name) { Toast.show('Choose a template'); return; }
        const t = State.templates.find((x) => x.name === name);
        if (!t) { Toast.show('Template not found'); return; }
        try { await API.resumeRun({ agent_run_id: r.id, prompt: t.text }); Toast.show(`Resumed #${r.id} with '${name}'`); }
        catch (e2) { console.error(e2); Toast.show('Resume failed'); }
      });
      adhocBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const txt = (adhoc.value || '').trim();
        if (!txt) { Toast.show('Enter a prompt'); return; }
        try { await API.resumeRun({ agent_run_id: r.id, prompt: txt }); Toast.show(`Resumed #${r.id}`); adhoc.value=''; }
        catch (e2) { console.error(e2); Toast.show('Resume failed'); }
      });
    }

    openBtn.addEventListener('click', (e) => { e.stopPropagation(); openLogs(r.id); });
    pinBtn.addEventListener('click', (e) => { e.stopPropagation(); if (State.pinned.has(r.id)) State.pinned.delete(r.id); else State.pinned.add(r.id); savePinned(); renderRuns(); });
    watchBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleWatch(r.id); });

    el.addEventListener('click', () => { el.classList.toggle('expanded'); });

    el.appendChild(title);
    el.appendChild(meta);
    if (r.web_url) { const link = document.createElement('a'); link.href = r.web_url; link.target='_blank'; link.rel='noreferrer noopener'; link.textContent = 'Open in Codegen'; el.appendChild(link); }
    el.appendChild(actions);
    el.appendChild(quick);
    return el;
  }

  function renderRuns() {
    const view = (viewSelect && viewSelect.value) || 'active';
    let list = [...State.runs];
    // Pinned first
    list.sort((a,b) => {
      const ap = State.pinned.has(a.id) ? 0 : 1;
      const bp = State.pinned.has(b.id) ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return (new Date(b.created_at||0)) - (new Date(a.created_at||0));
    });
    if (view === 'active') list = list.filter((r) => statusIsActive(r.status));
    if (view === 'past') list = list.filter((r) => !statusIsActive(r.status));
    runsListEl.innerHTML = '';
    list.forEach((r) => runsListEl.appendChild(runCard(r)));
    renderActiveHeader();
  }

  async function refreshRuns() {
    try {
      // Auto-refresh; get last 100
      const res = await API.listRuns({ limit: 100 });
      State.runs = res.items || [];
      const parts = partitionRuns(State.runs);
      State.active = parts.active; State.past = parts.past;
      renderRuns();
    } catch (e) {
      console.error(e);
    }
  }

  // Watchers: poll getRun every 10s
  function ensureWatch(id) {
    if (State.watchers.has(id)) return;
    const h = setInterval(async () => {
      try {
        const r = await API.getRun(id);
        const old = State.runs.find((x) => x.id === id) || {};
        // Update in place
        const idx = State.runs.findIndex((x) => x.id === id);
        if (idx >= 0) State.runs[idx] = r; else State.runs.push(r);
        const parts = partitionRuns(State.runs);
        State.active = parts.active; State.past = parts.past;
        renderRuns();
        // Completion detection for chaining
        if (old.status !== undefined && statusIsActive(old.status) && !statusIsActive(r.status)) {
          // Completed now
          Toast.show(`Run #${id} completed`);
          // Auto-chain if configured on this run
          notify('Run complete', `#${id} is complete`);

          if (r.__chainPlan && Array.isArray(r.__chainPlan) && r.__chainIndex < r.__chainPlan.length) {
            const step = r.__chainPlan[r.__chainIndex];
            const tpl = State.templates.find((t) => t.name === step.name);
            if (tpl) {
              try {
                await API.resumeRun({ agent_run_id: id, prompt: tpl.text });
                Toast.show(`Auto-chained #${id} with '${step.name}'`);
                r.__chainIndex += 1;
                // Continue watching; next completion will trigger next chaining
              } catch (e) {
                console.error(e); Toast.show('Auto-chaining failed');
              }
            }
          }
        }
      } catch (e) { console.error(e); }
    }, 10000);
    State.watchers.set(id, h);
  }
  function toggleWatch(id) {
    if (State.watchers.has(id)) {
      clearInterval(State.watchers.get(id));
      State.watchers.delete(id);
      Toast.show(`Stopped watching #${id}`);
    } else {
      ensureWatch(id);
      Toast.show(`Watching #${id}`);
    }
  }

  // Logs modal stream (polling)
  let currentLogsId = null;
  let logsPaused = false;
  pauseLogsBtn.addEventListener('click', () => {
    logsPaused = !logsPaused;
    pauseLogsBtn.textContent = logsPaused ? 'Resume' : 'Pause';
  });
  copyLogsBtn.addEventListener('click', async () => {
    try {
      const text = logsContainer.textContent || '';
      await navigator.clipboard.writeText(text);
      Toast.show('Logs copied');
    } catch {}
  });

  async function openLogs(id) {
    currentLogsId = id; logsPaused = false; pauseLogsBtn.textContent = 'Pause';
    logsRunId.textContent = `#${id}`;
    logsContainer.textContent = '';
    showLogsModal();
    // Start polling loop
    let skip = 0; const limit = 100; let stop = false;
    const poll = async () => {
      if (stop) return;
      try {
        const res = await API.getRunLogs(id, { skip, limit, reverse: false });
        const logs = res.logs || [];
        if (!logsPaused && logs.length) {
          logs.forEach((l) => {
            const line = `[${l.created_at || ''}] ${l.message_type || ''}${l.tool_name ? ' ['+l.tool_name+']' : ''}\n` +
                         (l.thought ? `thought: ${l.thought}\n` : '') +
                         (l.tool_input ? `input: ${JSON.stringify(l.tool_input)}\n` : '') +
                         (l.tool_output ? `output: ${JSON.stringify(l.tool_output)}\n` : '') + `\n`;
            logsContainer.textContent += line;
          });
          logsContainer.scrollTop = logsContainer.scrollHeight;
          skip += logs.length;
        }
      } catch (e) { /* swallow */ }
      setTimeout(poll, 2000);
    };
    const obs = new MutationObserver((m) => {
      // If modal gets hidden, stop this loop by flipping stop flag
      const hidden = document.getElementById('logsModal').classList.contains('hidden');
      if (hidden) stop = true; else stop = false;
    });
    obs.observe(document.getElementById('logsModal'), { attributes: true, attributeFilter: ['class'] });
    poll();
  }

  // Periodic refresh of active count and lists (no manual refresh button)
  async function periodicRefresh() {
    await refreshRuns();
    const hidden = document.hidden;
    setTimeout(periodicRefresh, hidden ? 25000 : 15000);
  }

  // Init
  renderTemplates();
  periodicRefresh();
})();
