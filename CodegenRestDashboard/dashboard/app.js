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
  const pinnedListEl = document.getElementById('pinnedList');
  const filterRadios = document.querySelectorAll('input[name="filter"]');
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

  // Filter
  filterRadios.forEach((r) => r.addEventListener('change', renderRuns));

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

    const title = document.createElement('div');
    title.textContent = `#${r.id}`;
    const meta = document.createElement('div');
    meta.className = 'meta';
    const d = new Date(r.created_at || Date.now());
    const statusCls = statusIsActive(r.status) ? 'active' : 'past';
    meta.innerHTML = `<span class="status ${statusCls}">${r.status || ''}</span> <span>${d.toLocaleString()}</span>`;

    const actions = document.createElement('div');
    actions.className = 'actions';

    const openBtn = document.createElement('button'); openBtn.textContent = 'Open Logs';
    const pinBtn = document.createElement('button'); pinBtn.textContent = State.pinned.has(r.id) ? 'Unpin' : 'Pin';
    const watchBtn = document.createElement('button'); watchBtn.textContent = State.watchers.has(r.id) ? 'Unwatch' : 'Watch';

    const resumeSel = document.createElement('select');
    const emptyOpt = document.createElement('option'); emptyOpt.value=''; emptyOpt.textContent = '(choose template)'; resumeSel.appendChild(emptyOpt);
    State.templates.forEach((t) => { const o = document.createElement('option'); o.value=t.name; o.textContent=t.name; resumeSel.appendChild(o); });
    const resumeBtn = document.createElement('button'); resumeBtn.textContent = 'Resume with Template';

    const chainSel = document.createElement('select'); chainSel.multiple = true; chainSel.size = 3; chainSel.style.minWidth = '160px';
    State.templates.forEach((t) => { const o = document.createElement('option'); o.value=t.name; o.textContent=t.name; chainSel.appendChild(o); });
    const applyChainBtn = document.createElement('button'); applyChainBtn.textContent = 'Apply Chaining';

    actions.appendChild(openBtn);
    actions.appendChild(pinBtn);
    actions.appendChild(watchBtn);
    actions.appendChild(resumeSel);
    actions.appendChild(resumeBtn);
    actions.appendChild(chainSel);
    actions.appendChild(applyChainBtn);

    openBtn.addEventListener('click', () => openLogs(r.id));
    pinBtn.addEventListener('click', () => {
      if (State.pinned.has(r.id)) State.pinned.delete(r.id); else State.pinned.add(r.id);
      savePinned(); renderAll();
    });
    watchBtn.addEventListener('click', () => toggleWatch(r.id));

    resumeBtn.addEventListener('click', async () => {
      const name = resumeSel.value;
      if (!name) { Toast.show('Choose a template'); return; }
      const t = State.templates.find((x) => x.name === name);
      if (!t) { Toast.show('Template not found'); return; }
      try {
        await API.resumeRun({ agent_run_id: r.id, prompt: t.text });
        Toast.show(`Resumed #${r.id} with '${name}'`);
      } catch (e) {
        console.error(e); Toast.show('Resume failed');
      }
    });

    applyChainBtn.addEventListener('click', () => {
      const selected = Array.from(chainSel.selectedOptions).map((o) => o.value).filter(Boolean);
      if (selected.length === 0) { Toast.show('Select templates'); return; }
      // Register chaining plan on this run id
      const plan = selected.map((nm) => ({ name: nm }));
      r.__chainPlan = plan; r.__chainIndex = 0; r.__lastState = r.status || '';
      Toast.show(`Chaining set on #${r.id}: ${selected.join(' -> ')}`);
      // Start watching automatically
      ensureWatch(r.id);
    });

    el.appendChild(title);
    el.appendChild(meta);
    if (r.web_url) {
      const link = document.createElement('a'); link.href = r.web_url; link.target='_blank'; link.rel='noreferrer noopener'; link.textContent = 'Open in Codegen';
      el.appendChild(link);
    }
    el.appendChild(actions);
    return el;
  }

  function renderRuns() {
    const filter = document.querySelector('input[name="filter"]:checked').value;
    const source = filter === 'active' ? State.active : State.past;
    runsListEl.innerHTML = '';
    source.forEach((r) => runsListEl.appendChild(runCard(r)));
    // Pinned at top area
    const pinned = State.runs.filter((r) => State.pinned.has(r.id));
    pinnedListEl.innerHTML = '';
    pinned.forEach((r) => pinnedListEl.appendChild(runCard(r)));
    document.getElementById('pinnedContainer').style.display = pinned.length ? 'block' : 'none';
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

