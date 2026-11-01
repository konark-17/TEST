// GitFlow Dashboard Front-End JavaScript

let currentStatus = null;
let activeTab = 'single';

document.addEventListener('DOMContentLoaded', () => {
  lucide.createIcons();
  refreshAll();
  setupDropzone();
  setupLogPolling();
});

// Toast notification system
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `pointer-events-auto flex items-center space-x-2 px-4 py-3 rounded-xl border shadow-xl text-xs font-medium transition transform translate-y-2 opacity-0 ${
    type === 'success'
      ? 'bg-slate-900 border-emerald-500/40 text-emerald-300'
      : type === 'error'
      ? 'bg-slate-900 border-red-500/40 text-red-300'
      : 'bg-slate-900 border-slate-700 text-slate-200'
  }`;

  const iconName = type === 'success' ? 'check-circle' : type === 'error' ? 'alert-triangle' : 'info';
  toast.innerHTML = `<i data-lucide="${iconName}" class="w-4 h-4 shrink-0"></i><span>${message}</span>`;
  container.appendChild(toast);
  lucide.createIcons();

  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Fetch complete system status
async function refreshAll() {
  const refreshIcon = document.getElementById('refreshIcon');
  if (refreshIcon) refreshIcon.classList.add('animate-spin');

  try {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error('Failed to fetch status');
    currentStatus = await res.json();
    renderDashboard(currentStatus);
  } catch (err) {
    showToast('Failed to load status: ' + err.message, 'error');
  } finally {
    if (refreshIcon) {
      setTimeout(() => refreshIcon.classList.remove('animate-spin'), 500);
    }
  }
}

// Render Dashboard Data
function renderDashboard(data) {
  const cfg = data.config || {};
  const queue = data.queue || [];
  const history = data.history || [];
  const sched = data.scheduler || {};
  const stats = data.stats || {};

  // Author & Stats
  document.getElementById('authorName').innerText = `${cfg.git_user_name || 'konark-17'}`;
  document.getElementById('statQueueCount').innerText = queue.length;
  document.getElementById('queueCountBadge').innerText = queue.length;
  document.getElementById('statCommittedCount').innerText = history.length;
  document.getElementById('historyCount').innerText = history.length;

  // Active Repos
  const repoNames = Object.keys(cfg.repos || {});
  const totalRepos = repoNames.length;
  document.getElementById('statRepoCount').innerText = totalRepos;
  document.getElementById('statActiveRepo').innerText = totalRepos > 0 ? `${totalRepos} repos tracked` : 'No repo configured';

  // Scheduler state
  const schedState = document.getElementById('statSchedulerState');
  const schedNext = document.getElementById('statSchedulerNext');
  const schedBadge = document.getElementById('schedulerBadge');

  if (sched.installed) {
    schedState.innerText = `Active (${cfg.schedule_time || '10:00'})`;
    schedState.className = 'text-base font-bold text-emerald-400';
    schedNext.innerText = `Next: ${sched.next_run || 'Tomorrow'}`;
    schedBadge.innerText = 'Installed';
    schedBadge.className = 'text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
  } else {
    schedState.innerText = 'Disabled';
    schedState.className = 'text-base font-bold text-slate-400';
    schedNext.innerText = 'No background task';
    schedBadge.innerText = 'Disabled';
    schedBadge.className = 'text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700';
  }

  // GitHub Sync Status Pill in Header
  const sync = data.sync || {};
  const syncDot = document.getElementById('syncDot');
  const syncText = document.getElementById('syncStatusText');
  if (syncDot && syncText) {
    if (!sync.configured) {
      syncDot.className = 'w-2 h-2 rounded-full bg-slate-500';
      syncText.innerText = 'Connect GitHub';
    } else if (!sync.connected) {
      syncDot.className = 'w-2 h-2 rounded-full bg-red-500 animate-pulse';
      syncText.innerText = 'GitHub Offline';
    } else if (sync.ahead > 0) {
      syncDot.className = 'w-2 h-2 rounded-full bg-amber-400 animate-pulse';
      syncText.innerText = `${sync.ahead} Unpushed (${sync.repo_name || 'main'})`;
    } else if (sync.behind > 0) {
      syncDot.className = 'w-2 h-2 rounded-full bg-blue-400';
      syncText.innerText = `${sync.behind} to Pull (${sync.repo_name || 'main'})`;
    } else {
      syncDot.className = 'w-2 h-2 rounded-full bg-emerald-400';
      syncText.innerText = `In Sync (${sync.repo_name || 'main'})`;
    }
  }

  // Populate Repo Selectors
  populateRepoDropdowns(cfg);

  // Render Repositories Cards
  renderRepoCards(cfg);

  // Render Queue Table
  renderQueueTable(queue);

  // Render History Table
  renderHistoryTable(history, cfg);

  // Render Contribution Heatmap
  renderContributionHeatmap(history);

  // Update Settings inputs
  document.getElementById('settingsAuthorName').value = cfg.git_user_name || '';
  document.getElementById('settingsAuthorEmail').value = cfg.git_user_email || '';
  document.getElementById('settingsRemoteUrl').value = cfg.remote_url || '';
  document.getElementById('settingsAutoPush').checked = cfg.auto_push ?? true;
  document.getElementById('schedulerTimeInput').value = cfg.schedule_time || '10:00';

  lucide.createIcons();
}

// Populate Repo Dropdowns across the page
function populateRepoDropdowns(cfg) {
  const repos = Object.keys(cfg.repos || {});

  const updateSelect = (selectId, includeAll = false, placeholder = '-- Select Target Repo (Required) --') => {
    const el = document.getElementById(selectId);
    if (!el) return;
    const currVal = el.value;
    el.innerHTML = '';

    if (includeAll) {
      el.innerHTML += `<option value="ALL">All Repositories</option>`;
    } else if (repos.length === 0) {
      el.innerHTML += `<option value="" disabled selected>-- No Repositories (Add One Above) --</option>`;
    } else {
      el.innerHTML += `<option value="" disabled ${!currVal ? 'selected' : ''}>${placeholder}</option>`;
    }

    repos.forEach(r => {
      const repoData = (cfg.repos || {})[r] || {};
      const remote = repoData.remote_url || '';
      const label = remote
        ? `${r} (${remote.replace('https://github.com/', '').replace('.git', '')})`
        : r;
      el.innerHTML += `<option value="${r}">${label}</option>`;
    });

    if (currVal && [...el.options].some(o => o.value === currVal)) {
      el.value = currVal;
    } else if (!includeAll && repos.length > 0 && !currVal) {
      // Auto-select first repo by default for convenience
      el.value = repos[0];
    }
  };

  updateSelect('dropzoneRepoSelect', false, '-- Select Target Repo (Required) --');
  updateSelect('singleUploadRepo', false, '-- Select Target Repo (Required) --');
  updateSelect('queueFilterRepo', true);
  updateSelect('modalSyncRepoSelect', false, '-- Select Repo to Sync --');
}

// Render Repositories List
function renderRepoCards(cfg) {
  const container = document.getElementById('repoCardsContainer');
  container.innerHTML = '';

  const repos = cfg.repos || {};
  const entries = Object.entries(repos);

  if (entries.length === 0) {
    container.innerHTML = `
      <div class="p-4 rounded-xl bg-slate-800/40 border border-slate-700/40 text-center text-slate-400 text-xs">
        No repositories configured yet. Click <strong class="text-purple-300">+ Add Repo</strong> or <strong class="text-blue-300">Sync All GitHub Repos</strong> to get started!
      </div>
    `;
    lucide.createIcons();
    return;
  }

  entries.forEach(([name, r]) => {
    const card = document.createElement('div');
    card.className = 'p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/60 space-y-2';
    const remoteDisplay = r.remote_url ? r.remote_url.replace('https://github.com/', '') : '(Local Commits Only)';
    const isCustomPath = !!r.repo_path;

    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="font-bold text-xs text-white">${name}</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 font-mono">${r.branch || 'main'}</span>
          ${isCustomPath ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">Custom Path</span>' : ''}
        </div>
        <div class="flex items-center space-x-1">
          ${r.remote_url ? `<button onclick="testRemoteUrl('${r.remote_url}')" class="p-1 hover:text-emerald-400 text-slate-400" title="Test Connection"><i data-lucide="wifi" class="w-3.5 h-3.5"></i></button>` : ''}
          <button onclick="deleteRepo('${name}')" class="p-1 hover:text-red-400 text-slate-400" title="Delete Repo"><i data-lucide="trash" class="w-3.5 h-3.5"></i></button>
        </div>
      </div>
      <div class="text-[11px] text-slate-400 truncate font-mono">
        ${remoteDisplay}
      </div>
    `;
    container.appendChild(card);
  });
  lucide.createIcons();
}

// Render Queue Table
function renderQueueTable(queue) {
  const tbody = document.getElementById('queueTableBody');
  const filter = document.getElementById('queueFilterRepo')?.value || 'ALL';
  tbody.innerHTML = '';

  const filtered = filter === 'ALL' ? queue : queue.filter(q => q.repo === filter);

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" class="py-8 text-center text-slate-500">
          No files in queue${filter !== 'ALL' ? ` for repo '${filter}'` : ''}. Drop some files above!
        </td>
      </tr>
    `;
    return;
  }

  filtered.forEach(item => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-800/40 transition group';
    tr.innerHTML = `
      <td class="py-3 px-3 font-mono font-medium text-white flex items-center space-x-2">
        <i data-lucide="file-code" class="w-4 h-4 text-blue-400 shrink-0"></i>
        <span class="truncate max-w-[200px]" title="${item.rel_path}">${item.name}</span>
      </td>
      <td class="py-3 px-3">
        <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/20">${item.repo}</span>
      </td>
      <td class="py-3 px-3 text-slate-400 font-mono text-[11px]">${item.size_str}</td>
      <td class="py-3 px-3 text-right space-x-1">
        <button onclick="previewFile('${item.rel_path}')" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition" title="Preview file">
          <i data-lucide="eye" class="w-3.5 h-3.5"></i>
        </button>
        <button onclick="triggerUploadFile('${item.repo}')" class="p-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 transition" title="Upload this file now">
          <i data-lucide="upload" class="w-3.5 h-3.5"></i>
        </button>
        <button onclick="deleteQueueFile('${item.rel_path}')" class="p-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 transition" title="Delete from queue">
          <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
  lucide.createIcons();
}

function filterQueueTable() {
  if (currentStatus) renderQueueTable(currentStatus.queue || []);
}

// Render Commit History Table
function renderHistoryTable(history, cfg) {
  const tbody = document.getElementById('historyTableBody');
  tbody.innerHTML = '';

  if (!history || history.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="py-6 text-center text-slate-500">
          No uploads committed yet.
        </td>
      </tr>
    `;
    return;
  }

  history.slice(0, 15).forEach(item => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-800/40 transition';
    const pushedBadge = item.pushed
      ? `<span class="text-emerald-400 flex items-center justify-end space-x-1"><i data-lucide="check" class="w-3 h-3"></i><span>Pushed</span></span>`
      : `<span class="text-slate-500 flex items-center justify-end space-x-1"><span>Local</span></span>`;

    tr.innerHTML = `
      <td class="py-2.5 px-3 font-mono text-emerald-400 font-semibold">${item.commit_hash || '---'}</td>
      <td class="py-2.5 px-3">
        <span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">${item.repo || 'Unassigned'}</span>
      </td>
      <td class="py-2.5 px-3 text-white truncate max-w-[150px]" title="${item.filename}">${item.filename}</td>
      <td class="py-2.5 px-3 text-slate-400 text-[11px]">${item.commit_date || item.timestamp}</td>
      <td class="py-2.5 px-3 text-right">${pushedBadge}</td>
    `;
    tbody.appendChild(tr);
  });
  lucide.createIcons();
}

// Render 60-Day Contribution Heatmap Matrix
function renderContributionHeatmap(history) {
  const container = document.getElementById('heatmapGrid');
  container.innerHTML = '';

  // Aggregate commits by YYYY-MM-DD
  const countsByDate = {};
  history.forEach(item => {
    const dateStr = (item.commit_date || item.timestamp || '').split(' ')[0];
    if (dateStr) {
      countsByDate[dateStr] = (countsByDate[dateStr] || 0) + 1;
    }
  });

  const now = new Date();
  const daysTotal = 70; // 10 weeks of 7 days
  const startDate = new Date();
  startDate.setDate(now.getDate() - daysTotal + 1);

  // Group into columns of 7 days (weeks)
  let currentWeekCol = document.createElement('div');
  currentWeekCol.className = 'flex flex-col gap-1.5';

  for (let i = 0; i < daysTotal; i++) {
    const d = new Date(startDate);
    d.setDate(startDate.getDate() + i);
    const dateKey = d.toISOString().split('T')[0];
    const count = countsByDate[dateKey] || 0;

    let bgClass = 'bg-slate-800';
    if (count === 1) bgClass = 'bg-emerald-800';
    else if (count === 2) bgClass = 'bg-emerald-600';
    else if (count >= 3) bgClass = 'bg-emerald-400';

    const cell = document.createElement('div');
    cell.className = `streak-cell ${bgClass} cursor-pointer`;
    cell.title = `${dateKey}: ${count} commit(s)`;
    currentWeekCol.appendChild(cell);

    if ((i + 1) % 7 === 0) {
      container.appendChild(currentWeekCol);
      currentWeekCol = document.createElement('div');
      currentWeekCol.className = 'flex flex-col gap-1.5';
    }
  }

  if (currentWeekCol.children.length > 0) {
    container.appendChild(currentWeekCol);
  }
}

// Drag & Drop Setup
function setupDropzone() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');

  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dropzone-active');
  });

  ['dragleave', 'dragend'].forEach(type => {
    dropzone.addEventListener(type, () => dropzone.classList.remove('dropzone-active'));
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dropzone-active');
    if (e.dataTransfer.files.length > 0) {
      handleFilesUpload(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFilesUpload(fileInput.files);
    }
  });
}

// Upload dropped files to queue endpoint
async function handleFilesUpload(fileList) {
  const repo = document.getElementById('dropzoneRepoSelect').value;
  if (!repo || repo === 'default') {
    showToast('Repository selection is compulsory! Please select a target repository before adding files.', 'error');
    return;
  }
  const formData = new FormData();
  formData.append('repo', repo);

  for (let i = 0; i < fileList.length; i++) {
    formData.append('files', fileList[i]);
  }

  showToast(`Uploading ${fileList.length} file(s) to '${repo}' queue...`, 'info');

  try {
    const res = await fetch('/api/queue/upload', {
      method: 'POST',
      body: formData,
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Added ${result.saved_count} file(s) to queue!`, 'success');
      refreshAll();
    } else {
      showToast('Upload failed: ' + result.message, 'error');
    }
  } catch (err) {
    showToast('Upload error: ' + err.message, 'error');
  }
}

// Trigger Single Upload
async function triggerSingleUpload() {
  const repo = document.getElementById('singleUploadRepo').value;
  if (!repo || repo === 'default') {
    showToast('Repository selection is compulsory! Please select a target repository.', 'error');
    return;
  }
  const dryRun = document.getElementById('singleDryRun').checked;

  showToast(dryRun ? `Simulating upload to '${repo}' (Dry-Run)...` : `Uploading next file to '${repo}'...`, 'info');

  try {
    const res = await fetch('/api/upload-single', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo: repo, dry_run: dryRun }),
    });
    const data = await res.json();
    if (data.success) {
      const msg = dryRun
        ? `[Dry-Run] Would upload ${data.file}`
        : `Uploaded ${data.file}! (${data.files_remaining} remaining)`;
      showToast(msg, 'success');
      refreshAll();
      fetchLogs();
    } else {
      showToast(`Upload failed: ${data.message}`, 'error');
    }
  } catch (err) {
    showToast('Failed to trigger: ' + err.message, 'error');
  }
}

async function triggerUploadFile(repoName) {
  document.getElementById('singleUploadRepo').value = repoName;
  triggerSingleUpload();
}

// Trigger Streak Spreader
async function triggerStreakSpreader() {
  const repo = document.getElementById('singleUploadRepo').value;
  if (!repo || repo === 'default') {
    showToast('Repository selection is compulsory! Please select a target repository.', 'error');
    return;
  }
  const count = parseInt(document.getElementById('streakFileCount').value) || 5;
  const daysBack = parseInt(document.getElementById('streakDaysBack').value) || 14;
  const dryRun = document.getElementById('streakDryRun').checked;

  showToast(`Executing Streak Spreader for ${count} files over ${daysBack} days in '${repo}'...`, 'info');

  try {
    const res = await fetch('/api/upload-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo: repo,
        count: count,
        spread_days: true,
        days_back: daysBack,
        dry_run: dryRun,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast('Streak Spreader completed!', 'success');
      refreshAll();
      fetchLogs();
    } else {
      showToast('Streak Spreader failed', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// Delete File from Queue
async function deleteQueueFile(filePath) {
  if (!confirm(`Remove '${filePath}' from queue?`)) return;

  try {
    const res = await fetch(`/api/queue/${encodeURIComponent(filePath)}`, {
      method: 'DELETE',
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Removed from queue`, 'success');
      refreshAll();
    }
  } catch (err) {
    showToast('Failed to delete file: ' + err.message, 'error');
  }
}

// Preview File Content Modal
async function previewFile(filePath) {
  try {
    const res = await fetch(`/api/queue/preview/${encodeURIComponent(filePath)}`);
    const data = await res.json();
    document.getElementById('previewTitle').innerText = data.filename;
    document.getElementById('previewContent').innerText = data.content || '(File is empty)';
    openModal('previewModal');
  } catch (err) {
    showToast('Failed to load preview: ' + err.message, 'error');
  }
}

// Windows Scheduler Commands
async function installScheduler() {
  const time = document.getElementById('schedulerTimeInput').value || '10:00';
  showToast(`Registering Windows daily task at ${time}...`, 'info');

  try {
    const res = await fetch('/api/scheduler/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ time: time }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      refreshAll();
    }
  } catch (err) {
    showToast('Failed to install scheduler: ' + err.message, 'error');
  }
}

async function removeScheduler() {
  if (!confirm('Disable and remove the Windows Daily Uploader task?')) return;
  showToast('Removing task...', 'info');

  try {
    const res = await fetch('/api/scheduler/remove', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Task removed', 'success');
      refreshAll();
    }
  } catch (err) {
    showToast('Failed to remove: ' + err.message, 'error');
  }
}

async function runSchedulerNow() {
  showToast('Triggering scheduled task now...', 'info');
  try {
    const res = await fetch('/api/scheduler/run-now', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Task triggered! Check logs in a few moments.', 'success');
      setTimeout(() => { refreshAll(); fetchLogs(); }, 3000);
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// Repositories Management
function openAddRepoModal() {
  const cfg = currentStatus?.config || {};
  const user = cfg.git_user_name || 'konark-17';
  const userInput = document.getElementById('githubFetchUser');
  if (userInput) userInput.value = user;

  switchRepoModalTab('github');
  fetchGitHubReposList();
  openModal('repoModal');
}

function switchRepoModalTab(tab) {
  const tabs = ['github', 'local', 'custom'];
  tabs.forEach(t => {
    const btn = document.getElementById(`repoTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
    const content = document.getElementById(`repoModalContent${t.charAt(0).toUpperCase() + t.slice(1)}`);
    if (t === tab) {
      if (btn) {
        btn.className = 'flex-1 pb-2.5 text-xs font-semibold text-purple-400 border-b-2 border-purple-400 transition flex items-center justify-center space-x-1.5';
      }
      if (content) content.classList.remove('hidden');
    } else {
      if (btn) {
        btn.className = 'flex-1 pb-2.5 text-xs font-semibold text-slate-400 hover:text-slate-200 transition flex items-center justify-center space-x-1.5';
      }
      if (content) content.classList.add('hidden');
    }
  });

  if (tab === 'local') {
    fetchLocalReposList();
  }
}

async function fetchGitHubReposList() {
  const listEl = document.getElementById('githubReposList');
  const user = document.getElementById('githubFetchUser')?.value.trim() || 'konark-17';
  const icon = document.getElementById('fetchReposIcon');
  if (icon) icon.classList.add('animate-spin');

  listEl.innerHTML = `<div class="py-8 text-center text-xs text-slate-400">Fetching repositories for <b>${user}</b> from GitHub...</div>`;

  try {
    const res = await fetch(`/api/github/user-repos?username=${encodeURIComponent(user)}`);
    const data = await res.json();
    listEl.innerHTML = '';

    if (!data.success || !data.repos || data.repos.length === 0) {
      listEl.innerHTML = `
        <div class="py-6 text-center text-xs text-slate-400">
          No public repositories found for '${user}' or rate limited.<br>
          <span class="text-slate-500">You can also add a repo manually in the "Custom URL" tab.</span>
        </div>
      `;
      return;
    }

    data.repos.forEach(repo => {
      const item = document.createElement('div');
      item.className = 'py-2.5 px-2 flex items-center justify-between hover:bg-slate-800/40 rounded-lg transition';
      const isAdded = repo.is_added;

      item.innerHTML = `
        <div class="min-w-0 flex-1 pr-3">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-xs text-white truncate font-mono">${repo.name}</span>
            <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700">${repo.default_branch || 'main'}</span>
            ${repo.is_private ? '<span class="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-300">Private</span>' : ''}
          </div>
          ${repo.description ? `<p class="text-[11px] text-slate-400 truncate mt-0.5">${repo.description}</p>` : ''}
        </div>
        <div>
          ${isAdded
            ? '<button disabled class="px-2.5 py-1 text-xs rounded bg-slate-800/80 text-emerald-400 border border-emerald-500/20 font-semibold cursor-default">✓ Added</button>'
            : `<button onclick="quickAddGitHubRepo('${repo.name}', '${repo.clone_url}', '${repo.default_branch || 'main'}')" class="px-2.5 py-1 text-xs rounded bg-purple-600 hover:bg-purple-500 text-white font-semibold transition shadow-sm">
                 + Add to Options
               </button>`
          }
        </div>
      `;
      listEl.appendChild(item);
    });
  } catch (err) {
    listEl.innerHTML = `<div class="py-6 text-center text-xs text-red-400">Failed to fetch GitHub repos: ${err.message}</div>`;
  } finally {
    if (icon) setTimeout(() => icon.classList.remove('animate-spin'), 500);
    lucide.createIcons();
  }
}

async function syncAllAccountRepos() {
  const user = document.getElementById('githubFetchUser')?.value.trim() || currentStatus?.config?.git_user_name || 'konark-17';
  showToast(`Syncing all repositories for @${user} from GitHub...`, 'info');

  const btn = document.getElementById('btnSyncAllRepos');
  if (btn) btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Syncing...</span>`;

  try {
    const res = await fetch('/api/github/sync-all-repos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Synced ${data.total_account_repos} repositories from @${user}! (${data.added_count} new added)`, 'success');
      await refreshAll();
      fetchGitHubReposList();
    } else {
      showToast(data.message || 'Failed to sync account repositories', 'error');
    }
  } catch (err) {
    showToast('Error syncing account: ' + err.message, 'error');
  } finally {
    if (btn) btn.innerHTML = `<i data-lucide="cloud-download" class="w-4 h-4"></i><span>Sync All Repos</span>`;
    lucide.createIcons();
  }
}

async function fetchLocalReposList() {
  const listEl = document.getElementById('localReposList');
  listEl.innerHTML = `<div class="py-8 text-center text-xs text-slate-400">Detecting local Git folders...</div>`;

  try {
    const res = await fetch('/api/repos/local-detected');
    const data = await res.json();
    listEl.innerHTML = '';

    if (!data.success || !data.local_repos || data.local_repos.length === 0) {
      listEl.innerHTML = `<div class="py-6 text-center text-xs text-slate-400">No other Git repositories detected in workspace directory.</div>`;
      return;
    }

    data.local_repos.forEach(lr => {
      const item = document.createElement('div');
      item.className = 'py-2.5 px-2 flex items-center justify-between hover:bg-slate-800/40 rounded-lg transition';
      const isAdded = lr.is_added;

      item.innerHTML = `
        <div class="min-w-0 flex-1 pr-3">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-xs text-white truncate font-mono">${lr.name}</span>
            <span class="text-[10px] px-1.5 py-0.2 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">${lr.branch}</span>
          </div>
          <p class="text-[11px] text-slate-400 truncate mt-0.5">${lr.remote_url || lr.path}</p>
        </div>
        <div>
          ${isAdded
            ? '<button disabled class="px-2.5 py-1 text-xs rounded bg-slate-800/80 text-emerald-400 border border-emerald-500/20 font-semibold cursor-default">✓ Linked</button>'
            : `<button onclick="quickAddLocalRepo('${lr.name}', '${lr.path.replace(/\\/g, '/')}', '${lr.remote_url}', '${lr.branch}')" class="px-2.5 py-1 text-xs rounded bg-purple-600 hover:bg-purple-500 text-white font-semibold transition shadow-sm">
                 + Link Project
               </button>`
          }
        </div>
      `;
      listEl.appendChild(item);
    });
  } catch (err) {
    listEl.innerHTML = `<div class="py-6 text-center text-xs text-red-400">Failed to detect local repos: ${err.message}</div>`;
  } finally {
    lucide.createIcons();
  }
}

async function quickAddGitHubRepo(name, cloneUrl, branch = 'main') {
  showToast(`Adding '${name}' to Target Repositories...`, 'info');

  try {
    const res = await fetch('/api/repos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        remote_url: cloneUrl,
        branch: branch,
        target_dir: `uploads/${name}`,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Repository '${name}' added to Target Options!`, 'success');
      closeModal('repoModal');
      await refreshAll();

      // Auto-select this newly added repo in dropdowns
      const dropSelect = document.getElementById('dropzoneRepoSelect');
      const singleSelect = document.getElementById('singleUploadRepo');
      if (dropSelect) dropSelect.value = name;
      if (singleSelect) singleSelect.value = name;
    } else {
      showToast('Failed to add repo: ' + (data.message || 'Error'), 'error');
    }
  } catch (err) {
    showToast('Error adding repo: ' + err.message, 'error');
  }
}

async function quickAddLocalRepo(name, path, remoteUrl = '', branch = 'main') {
  showToast(`Linking '${name}'...`, 'info');

  try {
    const res = await fetch('/api/repos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        repo_path: path,
        remote_url: remoteUrl,
        branch: branch,
        target_dir: 'uploads',
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Linked local repository '${name}'!`, 'success');
      closeModal('repoModal');
      await refreshAll();

      const dropSelect = document.getElementById('dropzoneRepoSelect');
      const singleSelect = document.getElementById('singleUploadRepo');
      if (dropSelect) dropSelect.value = name;
      if (singleSelect) singleSelect.value = name;
    } else {
      showToast('Failed to link repo', 'error');
    }
  } catch (err) {
    showToast('Error linking repo: ' + err.message, 'error');
  }
}

async function saveRepoProfile() {
  const name = document.getElementById('repoModalName').value.trim();
  const url = document.getElementById('repoModalUrl').value.trim();
  const branch = document.getElementById('repoModalBranch').value.trim() || 'main';
  const targetDir = document.getElementById('repoModalTargetDir').value.trim() || 'uploads';
  const repoPath = document.getElementById('repoModalPath').value.trim();

  if (!name) {
    alert('Profile name is required');
    return;
  }

  try {
    const res = await fetch('/api/repos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        remote_url: url,
        branch: branch,
        target_dir: targetDir,
        repo_path: repoPath,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Repository profile '${name}' saved!`, 'success');
      closeModal('repoModal');
      refreshAll();
    }
  } catch (err) {
    showToast('Failed to save repo: ' + err.message, 'error');
  }
}

async function deleteRepo(repoName) {
  if (!confirm(`Delete repository profile '${repoName}'?`)) return;

  try {
    const res = await fetch(`/api/repos/${encodeURIComponent(repoName)}`, {
      method: 'DELETE',
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Deleted repo profile '${repoName}'`, 'success');
      refreshAll();
    }
  } catch (err) {
    showToast('Failed to delete repo: ' + err.message, 'error');
  }
}

async function testRemoteUrl(url) {
  showToast('Testing remote repository connection...', 'info');
  try {
    const res = await fetch('/api/repos/test-remote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remote_url: url }),
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
  } catch (err) {
    showToast('Test failed: ' + err.message, 'error');
  }
}

function testRemoteFromModal() {
  const url = document.getElementById('repoModalUrl').value.trim();
  if (!url) {
    alert('Please enter a GitHub remote URL to test.');
    return;
  }
  testRemoteUrl(url);
}

// Global Settings Save
async function saveGlobalSettings() {
  const name = document.getElementById('settingsAuthorName').value.trim();
  const email = document.getElementById('settingsAuthorEmail').value.trim();
  const remoteUrl = document.getElementById('settingsRemoteUrl').value.trim();
  const autoPush = document.getElementById('settingsAutoPush').checked;

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        git_user_name: name,
        git_user_email: email,
        remote_url: remoteUrl,
        auto_push: autoPush,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast('Settings saved!', 'success');
      closeModal('settingsModal');
      refreshAll();
    }
  } catch (err) {
    showToast('Failed to save settings: ' + err.message, 'error');
  }
}

// Log Polling
async function fetchLogs() {
  const consoleEl = document.getElementById('logConsole');
  try {
    const res = await fetch('/api/logs?lines=60');
    const data = await res.json();
    const lines = data.logs || [];
    consoleEl.innerHTML = '';
    lines.forEach(line => {
      const div = document.createElement('div');
      div.innerText = line;
      if (line.includes('[ERROR]')) div.className = 'text-red-400';
      else if (line.includes('[WARNING]')) div.className = 'text-amber-400';
      else if (line.includes('[SUCCESS]')) div.className = 'text-emerald-400 font-semibold';
      else if (line.includes('[DRY-RUN]')) div.className = 'text-blue-400';
      consoleEl.appendChild(div);
    });
    consoleEl.scrollTop = consoleEl.scrollHeight;
  } catch (err) {
    console.error('Log fetch error', err);
  }
}

function setupLogPolling() {
  fetchLogs();
  setInterval(fetchLogs, 4000);
}

// Tab Switching
function switchTab(tab) {
  activeTab = tab;
  const tabSingle = document.getElementById('tabSingle');
  const tabStreak = document.getElementById('tabStreak');
  const contentSingle = document.getElementById('contentSingle');
  const contentStreak = document.getElementById('contentStreak');

  if (tab === 'single') {
    tabSingle.className = 'flex-1 pb-2 text-xs font-semibold text-emerald-400 border-b-2 border-emerald-400 transition';
    tabStreak.className = 'flex-1 pb-2 text-xs font-semibold text-slate-400 hover:text-slate-200 transition';
    contentSingle.classList.remove('hidden');
    contentStreak.classList.add('hidden');
  } else {
    tabStreak.className = 'flex-1 pb-2 text-xs font-semibold text-amber-400 border-b-2 border-amber-400 transition';
    tabSingle.className = 'flex-1 pb-2 text-xs font-semibold text-slate-400 hover:text-slate-200 transition';
    contentStreak.classList.remove('hidden');
    contentSingle.classList.add('hidden');
  }
}

// GitHub Sync Functions
function openSyncModal() {
  const cfg = currentStatus?.config || {};
  const repos = Object.keys(cfg.repos || {});
  const select = document.getElementById('modalSyncRepoSelect');
  if (select) {
    select.innerHTML = '';
    if (repos.length === 0) {
      select.innerHTML = `<option value="" disabled selected>-- No Repositories Configured --</option>`;
    } else {
      repos.forEach(r => {
        select.innerHTML += `<option value="${r}">${r}</option>`;
      });
      select.value = repos[0];
    }
  }

  loadSyncModalStatus();
  openModal('syncModal');
}

async function loadSyncModalStatus() {
  const repo = document.getElementById('modalSyncRepoSelect')?.value;
  const pill = document.getElementById('modalSyncStatusPill');
  const aheadEl = document.getElementById('modalSyncAhead');
  const behindEl = document.getElementById('modalSyncBehind');
  const urlInput = document.getElementById('modalSyncRemoteUrl');
  const branchInput = document.getElementById('modalSyncBranch');

  if (!repo) {
    pill.innerText = 'No Repo Selected';
    pill.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-700 text-slate-300';
    return;
  }

  pill.innerText = 'Checking...';
  pill.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-700 text-slate-300';

  try {
    const res = await fetch(`/api/sync/status?repo=${encodeURIComponent(repo)}`);
    const data = await res.json();

    aheadEl.innerText = data.ahead || 0;
    behindEl.innerText = data.behind || 0;
    if (data.remote_url) urlInput.value = data.remote_url;
    if (data.branch) branchInput.value = data.branch;

    pill.innerText = data.status_text || 'Connected';
    if (data.badge_color === 'emerald') {
      pill.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    } else if (data.badge_color === 'amber') {
      pill.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20';
    } else if (data.badge_color === 'red') {
      pill.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20';
    } else {
      pill.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-700 text-slate-300';
    }
  } catch (err) {
    pill.innerText = 'Status check failed';
    pill.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-red-500/10 text-red-400';
  }
}

async function executeModalSync(action = 'sync') {
  const repo = document.getElementById('modalSyncRepoSelect')?.value;
  if (!repo) {
    showToast('Repository selection is compulsory! Please select a repository.', 'error');
    return;
  }
  const remoteUrl = document.getElementById('modalSyncRemoteUrl')?.value.trim();
  const branch = document.getElementById('modalSyncBranch')?.value.trim() || 'main';

  const actionText = action === 'push' ? 'Pushing commits...' : action === 'pull' ? 'Pulling from GitHub...' : 'Synchronizing with GitHub...';
  showToast(actionText, 'info');

  try {
    const res = await fetch('/api/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo: repo,
        remote_url: remoteUrl,
        branch: branch,
        action: action,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Sync successful!', 'success');
      loadSyncModalStatus();
      refreshAll();
      fetchLogs();
    } else {
      showToast(data.message || 'Sync failed', 'error');
    }
  } catch (err) {
    showToast('Sync error: ' + err.message, 'error');
  }
}

async function triggerQuickSync() {
  const syncIcon = document.getElementById('syncIcon');
  if (syncIcon) syncIcon.classList.add('animate-spin');
  showToast('Synchronizing with GitHub...', 'info');

  try {
    const res = await fetch('/api/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'sync' }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Sync complete!', 'success');
      refreshAll();
      fetchLogs();
    } else {
      showToast(data.message || 'Sync failed', 'error');
    }
  } catch (err) {
    showToast('Failed to sync: ' + err.message, 'error');
  } finally {
    if (syncIcon) setTimeout(() => syncIcon.classList.remove('animate-spin'), 600);
  }
}

function testSyncRemoteUrl() {
  const url = document.getElementById('modalSyncRemoteUrl')?.value.trim();
  if (!url) {
    alert('Please enter a GitHub repository remote URL.');
    return;
  }
  testRemoteUrl(url);
}

// Modal Helpers
function openModal(id) {
  document.getElementById(id).classList.remove('hidden');
  lucide.createIcons();
}

function closeModal(id) {
  document.getElementById(id).classList.add('hidden');
}

