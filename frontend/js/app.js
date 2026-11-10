// State Management
const state = {
  statements: [],
  activeStatementId: null,
  activeStatementData: null,
  selectedFiles: [],
  activeConversationId: null,
};

// DOM Elements
const elements = {
  dropzone: document.getElementById('dropzone'),
  fileInput: document.getElementById('file-input'),
  btnBrowse: document.getElementById('btn-browse'),
  selectedFilesList: document.getElementById('selected-files-list'),
  uploadActionsBar: document.getElementById('upload-actions-bar'),
  btnUpload: document.getElementById('btn-upload'),
  btnClearSelection: document.getElementById('btn-clear-selection'),
  btnProcessFolder: document.getElementById('btn-process-folder'),
  batchResultsPanel: document.getElementById('batch-results-panel'),
  batchFilesGrid: document.getElementById('batch-files-grid'),
  batchVerificationPill: document.getElementById('batch-verification-pill'),
  statementSelector: document.getElementById('statement-selector'),
  btnRefreshList: document.getElementById('btn-refresh-list'),
  btnDeleteStatement: document.getElementById('btn-delete-statement'),
  privacyStatusStrip: document.getElementById('privacy-status-strip'),
  statusGatePill: document.getElementById('status-gate-pill'),
  statusRedactionCount: document.getElementById('status-redaction-count'),
  statusBadgesContainer: document.getElementById('status-badges-container'),
  tabButtons: document.querySelectorAll('.tab-btn'),
  tabContents: document.querySelectorAll('.tab-content'),
  // Overview Tab
  kpiSpending: document.getElementById('kpi-spending'),
  kpiSpendingSub: document.getElementById('kpi-spending-sub'),
  kpiIncome: document.getElementById('kpi-income'),
  kpiIncomeSub: document.getElementById('kpi-income-sub'),
  kpiNet: document.getElementById('kpi-net'),
  kpiSubscriptions: document.getElementById('kpi-subscriptions'),
  kpiSubscriptionsSub: document.getElementById('kpi-subscriptions-sub'),
  transactionsTableBody: document.getElementById('transactions-table-body'),
  txSearchInput: document.getElementById('tx-search-input'),
  txTypeFilter: document.getElementById('tx-type-filter'),
  txCategoryFilter: document.getElementById('tx-category-filter'),
  // Scrubbed Tab
  scrubbedPreContent: document.getElementById('scrubbed-pre-content'),
  btnCopyScrubbed: document.getElementById('btn-copy-scrubbed'),
  btnDownloadScrubbed: document.getElementById('btn-download-scrubbed'),
  // Analysis Tab
  btnRunAnalysis: document.getElementById('btn-run-analysis'),
  analysisEmptyState: document.getElementById('analysis-empty-state'),
  analysisResultsView: document.getElementById('analysis-results-view'),
  analysisSummaryText: document.getElementById('analysis-summary-text'),
  analysisModelTag: document.getElementById('analysis-model-tag'),
  analysisCategoryBars: document.getElementById('analysis-category-bars'),
  analysisTopMerchantsList: document.getElementById('analysis-top-merchants-list'),
  analysisPatternsList: document.getElementById('analysis-patterns-list'),
  analysisSuggestionsList: document.getElementById('analysis-suggestions-list'),
  auditDiscrepancyNote: document.getElementById('audit-discrepancy-note'),
  // Chat Tab
  chatMessagesBox: document.getElementById('chat-messages-box'),
  chatInputForm: document.getElementById('chat-input-form'),
  chatTextInput: document.getElementById('chat-text-input'),
  quickPromptChips: document.querySelectorAll('.btn-chip'),
  toastContainer: document.getElementById('toast-container'),
};

// Utilities
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4000);
}

function formatCurrency(amount, currency = 'PKR') {
  const val = Number(amount) || 0;
  return `${currency} ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// 1. Ingestion: File Selection & Drag-and-Drop
elements.btnBrowse.addEventListener('click', () => elements.fileInput.click());
elements.dropzone.addEventListener('click', (e) => {
  if (e.target !== elements.btnBrowse) elements.fileInput.click();
});

elements.dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  elements.dropzone.classList.add('dragover');
});
elements.dropzone.addEventListener('dragleave', () => elements.dropzone.classList.remove('dragover'));
elements.dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  elements.dropzone.classList.remove('dragover');
  if (e.dataTransfer.files?.length) {
    handleFilesSelected(Array.from(e.dataTransfer.files));
  }
});

elements.fileInput.addEventListener('change', () => {
  if (elements.fileInput.files?.length) {
    handleFilesSelected(Array.from(elements.fileInput.files));
  }
});

function handleFilesSelected(newFiles) {
  state.selectedFiles = [...state.selectedFiles, ...newFiles];
  renderSelectedFilesChips();
}

function renderSelectedFilesChips() {
  elements.selectedFilesList.innerHTML = '';
  if (state.selectedFiles.length === 0) {
    elements.selectedFilesList.classList.add('hidden');
    elements.uploadActionsBar.classList.add('hidden');
    return;
  }
  elements.selectedFilesList.classList.remove('hidden');
  elements.uploadActionsBar.classList.remove('hidden');

  state.selectedFiles.forEach((file, index) => {
    const chip = document.createElement('div');
    chip.className = 'file-chip';
    chip.innerHTML = `
      <span>&#128196; ${escapeHtml(file.name)} (${(file.size / 1024).toFixed(1)} KB)</span>
      <button type="button" class="file-chip-remove" data-index="${index}">&times;</button>
    `;
    elements.selectedFilesList.appendChild(chip);
  });

  document.querySelectorAll('.file-chip-remove').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = Number(e.currentTarget.dataset.index);
      state.selectedFiles.splice(idx, 1);
      renderSelectedFilesChips();
    });
  });
}

elements.btnClearSelection.addEventListener('click', () => {
  state.selectedFiles = [];
  elements.fileInput.value = '';
  renderSelectedFilesChips();
});

// Upload Handlers
elements.btnUpload.addEventListener('click', async () => {
  if (state.selectedFiles.length === 0) return;
  const formData = new FormData();
  state.selectedFiles.forEach(f => formData.append('files', f));

  setButtonLoading(elements.btnUpload, true);
  try {
    const res = await fetch('/api/statements/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Upload failed');
    renderBatchReport(data);
    showToast(`Successfully processed ${data.successful_files} statement(s).`, 'success');
    state.selectedFiles = [];
    renderSelectedFilesChips();
    await loadStatementsList();
    if (data.files && data.files[0]?.statement_id) {
      selectStatement(data.files[0].statement_id);
    }
  } catch (err) {
    showToast(err.message, 'danger');
  } finally {
    setButtonLoading(elements.btnUpload, false);
  }
});

elements.btnProcessFolder.addEventListener('click', async () => {
  setButtonLoading(elements.btnProcessFolder, true);
  try {
    const res = await fetch('/api/statements/process-folder', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Folder processing failed');
    renderBatchReport(data);
    showToast(`Processed ${data.successful_files} statement(s) from data/ folder.`, 'success');
    await loadStatementsList();
    if (data.files && data.files[0]?.statement_id) {
      selectStatement(data.files[0].statement_id);
    }
  } catch (err) {
    showToast(err.message, 'danger');
  } finally {
    setButtonLoading(elements.btnProcessFolder, false);
  }
});

function renderBatchReport(batch) {
  elements.batchResultsPanel.classList.remove('hidden');
  elements.batchVerificationPill.className = `pill ${batch.verification_passed ? 'pill-success' : 'pill-danger'}`;
  elements.batchVerificationPill.textContent = batch.verification_passed ? 'Verified Safe' : 'Verification Flagged';
  elements.batchFilesGrid.innerHTML = '';

  batch.files.forEach(f => {
    const card = document.createElement('div');
    card.className = 'batch-file-card';
    const statusPill = f.status === 'success' ? 'pill-success' : (f.status === 'unsupported' ? 'pill-warning' : 'pill-danger');
    card.innerHTML = `
      <div class="batch-file-title">
        <span>${escapeHtml(f.filename)}</span>
        <span class="pill ${statusPill}">${f.status}</span>
      </div>
      <div class="batch-file-meta">
        Type: ${f.file_type.toUpperCase()} | Redactions: ${f.redaction_count || 0}
      </div>
      ${f.error_message ? `<div class="batch-file-meta text-danger">${escapeHtml(f.error_message)}</div>` : ''}
    `;
    elements.batchFilesGrid.appendChild(card);
  });
}

// 2. Statements List & Selection
async function loadStatementsList() {
  try {
    const res = await fetch('/api/statements');
    if (!res.ok) throw new Error('Could not fetch statements');
    state.statements = await res.json();
    populateStatementDropdown();
  } catch (err) {
    showToast('Failed to load statement records.', 'danger');
  }
}

function populateStatementDropdown() {
  elements.statementSelector.innerHTML = '';
  if (state.statements.length === 0) {
    elements.statementSelector.innerHTML = '<option value="">-- No statements in database --</option>';
    elements.btnDeleteStatement.disabled = true;
    elements.btnRunAnalysis.disabled = true;
    return;
  }
  state.statements.forEach(stmt => {
    const opt = document.createElement('option');
    opt.value = stmt.id;
    opt.textContent = `${stmt.original_filename} (${stmt.file_type.toUpperCase()}) - ${new Date(stmt.created_at).toLocaleDateString()}`;
    elements.statementSelector.appendChild(opt);
  });

  const targetId = state.activeStatementId || state.statements[0].id;
  elements.statementSelector.value = targetId;
  selectStatement(targetId);
}

elements.statementSelector.addEventListener('change', (e) => {
  if (e.target.value) selectStatement(e.target.value);
});
elements.btnRefreshList.addEventListener('click', loadStatementsList);

async function selectStatement(statementId) {
  state.activeStatementId = statementId;
  elements.btnDeleteStatement.disabled = false;
  elements.btnRunAnalysis.disabled = false;

  try {
    const [detailRes, txRes, scrubbedRes] = await Promise.all([
      fetch(`/api/statements/${statementId}`),
      fetch(`/api/statements/${statementId}/transactions`),
      fetch(`/api/statements/${statementId}/scrubbed`),
    ]);

    const detail = await detailRes.json();
    const txData = await txRes.json();
    const scrubbed = await scrubbedRes.json();

    state.activeStatementData = { detail, txData, scrubbed };

    renderPrivacyStrip(detail);
    renderOverviewAndTransactions(txData);
    renderScrubbedPreview(scrubbed);
    await checkExistingAnalysis(statementId);

  } catch (err) {
    showToast('Failed to load statement details.', 'danger');
  }
}

// Render Privacy Status Strip
function renderPrivacyStrip(detail) {
  elements.privacyStatusStrip.classList.remove('hidden');
  const passed = detail.verification_status === 'passed';
  elements.statusGatePill.className = `pill ${passed ? 'pill-success' : 'pill-danger'}`;
  elements.statusGatePill.textContent = passed ? 'PASSED' : 'BLOCKED';

  let totalRedactions = 0;
  elements.statusBadgesContainer.innerHTML = '';
  if (detail.redaction_summary) {
    for (const [tag, count] of Object.entries(detail.redaction_summary)) {
      totalRedactions += count;
      const badge = document.createElement('span');
      badge.className = 'badge-count';
      badge.textContent = `${tag}: ${count}`;
      elements.statusBadgesContainer.appendChild(badge);
    }
  }
  elements.statusRedactionCount.textContent = totalRedactions;
}

// Render Overview & Transactions
function renderOverviewAndTransactions(txData) {
  const sum = txData.summary || {};
  const curr = sum.currency || 'PKR';
  elements.kpiSpending.textContent = formatCurrency(sum.total_spending, curr);
  elements.kpiSpendingSub.textContent = `${sum.debit_count || 0} debit expenses`;
  elements.kpiIncome.textContent = formatCurrency(sum.total_income, curr);
  elements.kpiIncomeSub.textContent = `${sum.credit_count || 0} deposits`;
  elements.kpiNet.textContent = formatCurrency(sum.net_cashflow, curr);
  elements.kpiNet.className = `kpi-value ${sum.net_cashflow >= 0 ? 'text-success' : 'text-danger'}`;

  const subTotal = sum.subscription_expenses?.total || 0;
  elements.kpiSubscriptions.textContent = formatCurrency(subTotal, curr);
  elements.kpiSubscriptionsSub.textContent = `${sum.subscription_expenses?.items?.length || 0} subscription plan(s)`;

  // Populate Category Filter dropdown
  elements.txCategoryFilter.innerHTML = '<option value="all">All Categories</option>';
  const categories = Object.keys(sum.spending_by_category || {});
  categories.forEach(cat => {
    const opt = document.createElement('option');
    opt.value = cat;
    opt.textContent = cat;
    elements.txCategoryFilter.appendChild(opt);
  });

  renderFilteredTransactions();
}

function renderFilteredTransactions() {
  if (!state.activeStatementData?.txData?.transactions) return;
  const transactions = state.activeStatementData.txData.transactions;
  const searchQuery = (elements.txSearchInput.value || '').toLowerCase();
  const typeFilter = elements.txTypeFilter.value;
  const catFilter = elements.txCategoryFilter.value;

  const filtered = transactions.filter(t => {
    if (typeFilter !== 'all' && t.transaction_type !== typeFilter) return false;
    if (catFilter !== 'all' && t.category !== catFilter) return false;
    if (searchQuery) {
      const match = t.merchant_name.toLowerCase().includes(searchQuery)
        || t.description.toLowerCase().includes(searchQuery)
        || t.category.toLowerCase().includes(searchQuery);
      if (!match) return false;
    }
    return true;
  });

  elements.transactionsTableBody.innerHTML = '';
  if (filtered.length === 0) {
    elements.transactionsTableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No matching transactions found.</td></tr>';
    return;
  }

  filtered.forEach(t => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(t.transaction_date)}</td>
      <td><strong>${escapeHtml(t.merchant_name)}</strong></td>
      <td>${escapeHtml(t.description)}</td>
      <td><span class="pill pill-neutral">${escapeHtml(t.category)}</span></td>
      <td><span class="pill ${t.transaction_type === 'Credit' ? 'pill-success' : 'pill-neutral'}">${t.transaction_type}</span></td>
      <td class="text-right ${t.transaction_type === 'Credit' ? 'text-success' : ''}"><strong>${formatCurrency(t.amount, t.currency)}</strong></td>
      <td class="text-right">${t.balance !== null ? formatCurrency(t.balance, t.currency) : '-'}</td>
    `;
    elements.transactionsTableBody.appendChild(tr);
  });
}

elements.txSearchInput.addEventListener('input', renderFilteredTransactions);
elements.txTypeFilter.addEventListener('change', renderFilteredTransactions);
elements.txCategoryFilter.addEventListener('change', renderFilteredTransactions);

// Render Scrubbed Preview Tab
function renderScrubbedPreview(scrubbed) {
  elements.scrubbedPreContent.textContent = scrubbed.scrubbed_content || 'No content available.';
}

elements.btnCopyScrubbed.addEventListener('click', () => {
  navigator.clipboard.writeText(elements.scrubbedPreContent.textContent);
  showToast('Scrubbed statement copied to clipboard.', 'success');
});
elements.btnDownloadScrubbed.addEventListener('click', () => {
  const blob = new Blob([elements.scrubbedPreContent.textContent], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `scrubbed_${state.activeStatementData?.detail?.original_filename || 'statement'}.txt`;
  a.click();
});

// 3. AI Budget Insights Tab
elements.btnRunAnalysis.addEventListener('click', async () => {
  if (!state.activeStatementId) return;
  setButtonLoading(elements.btnRunAnalysis, true);
  try {
    const res = await fetch(`/api/statements/${state.activeStatementId}/analyze`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Analysis generation failed');
    renderAnalysisData(data.analysis, data.model_name);
    showToast('AI Budget Insights generated successfully.', 'success');
  } catch (err) {
    showToast(err.message, 'danger');
  } finally {
    setButtonLoading(elements.btnRunAnalysis, false);
  }
});

async function checkExistingAnalysis(statementId) {
  elements.analysisEmptyState.classList.remove('hidden');
  elements.analysisResultsView.classList.add('hidden');
  try {
    const res = await fetch(`/api/statements/${statementId}/analysis`);
    if (res.ok) {
      const data = await res.json();
      renderAnalysisData(data.analysis, data.model_name);
    }
  } catch (err) {
    // No analysis yet; empty state remains visible
  }
}

function renderAnalysisData(analysis, modelName) {
  elements.analysisEmptyState.classList.add('hidden');
  elements.analysisResultsView.classList.remove('hidden');

  const ai = analysis.ai_generated_observations || {};
  const confirmed = analysis.confirmed_transaction_data || {};
  const estimated = analysis.estimated_spending_categories || {};
  const audit = analysis.verification_and_accuracy_audit || {};

  elements.analysisSummaryText.textContent = ai.executive_summary || 'Budget report generated.';
  elements.analysisModelTag.textContent = `Model: ${modelName || 'Groq AI'} | Deterministic Reconciliation: Active`;

  // Spending Category Bars
  elements.analysisCategoryBars.innerHTML = '';
  const cats = estimated.spending_by_category || {};
  const totalSpend = confirmed.total_spending || 1;
  for (const [cat, amt] of Object.entries(cats)) {
    const pct = Math.min(100, (amt / totalSpend) * 100).toFixed(1);
    const row = document.createElement('div');
    row.className = 'category-bar-row';
    row.innerHTML = `
      <div class="category-bar-header">
        <span>${escapeHtml(cat)}</span>
        <span>${formatCurrency(amt, confirmed.currency)} (${pct}%)</span>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width: ${pct}%"></div></div>
    `;
    elements.analysisCategoryBars.appendChild(row);
  }

  // Top Merchants
  elements.analysisTopMerchantsList.innerHTML = '';
  (confirmed.top_merchants || []).slice(0, 6).forEach(m => {
    const li = document.createElement('li');
    li.style.marginBottom = '6px';
    li.innerHTML = `<strong>${escapeHtml(m.merchant)}</strong>: ${formatCurrency(m.total_spent, confirmed.currency)} <span class="hint-text">(${m.transaction_count} payments)</span>`;
    elements.analysisTopMerchantsList.appendChild(li);
  });

  // Patterns
  elements.analysisPatternsList.innerHTML = '';
  (ai.monthly_spending_patterns || []).forEach(p => {
    const li = document.createElement('li');
    li.textContent = p;
    elements.analysisPatternsList.appendChild(li);
  });

  // Suggestions
  elements.analysisSuggestionsList.innerHTML = '';
  (ai.practical_budgeting_suggestions || []).forEach(s => {
    const li = document.createElement('li');
    li.textContent = s;
    elements.analysisSuggestionsList.appendChild(li);
  });

  // Discrepancy Note
  if (audit.corrections_applied?.length) {
    elements.auditDiscrepancyNote.textContent = audit.corrections_applied.join(' ');
  } else {
    elements.auditDiscrepancyNote.textContent = 'All LLM reported totals matched deterministic Python calculations.';
  }
}

// 4. Grounded AI Chat Assistant
elements.chatInputForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = elements.chatTextInput.value.trim();
  if (!q || !state.activeStatementId) return;

  appendChatMessage('user', q);
  elements.chatTextInput.value = '';
  setButtonLoading(document.getElementById('btn-chat-send'), true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        statement_id: state.activeStatementId,
        question: q,
        conversation_id: state.activeConversationId,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Chat request failed');
    state.activeConversationId = data.conversation_id;
    appendChatMessage('assistant', data.answer);
  } catch (err) {
    appendChatMessage('assistant', `We couldn't reach the AI assistant right now: ${err.message}`);
  } finally {
    setButtonLoading(document.getElementById('btn-chat-send'), false);
  }
});

elements.quickPromptChips.forEach(chip => {
  chip.addEventListener('click', () => {
    elements.chatTextInput.value = chip.dataset.prompt;
    elements.chatInputForm.dispatchEvent(new Event('submit'));
  });
});

function appendChatMessage(role, text) {
  const msgDiv = document.createElement('div');
  msgDiv.className = `chat-msg ${role}`;
  msgDiv.innerHTML = `<div class="msg-bubble">${formatMarkdownToHtml(text)}</div>`;
  elements.chatMessagesBox.appendChild(msgDiv);
  elements.chatMessagesBox.scrollTop = elements.chatMessagesBox.scrollHeight;
}

function formatMarkdownToHtml(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}

// 5. Statement Deletion
elements.btnDeleteStatement.addEventListener('click', async () => {
  if (!state.activeStatementId) return;
  const name = state.activeStatementData?.detail?.original_filename || 'this statement';
  if (!confirm(`Are you sure you want to permanently delete "${name}" and all its transactions, insights, and chat history?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/statements/${state.activeStatementId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Deletion failed');
    showToast('Statement and all associated records deleted permanently.', 'success');
    state.activeStatementId = null;
    state.activeStatementData = null;
    await loadStatementsList();
  } catch (err) {
    showToast(err.message, 'danger');
  }
});

// Tab Switching
elements.tabButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    elements.tabButtons.forEach(b => b.classList.remove('active'));
    elements.tabContents.forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
  });
});

function setButtonLoading(btn, isLoading) {
  const spinner = btn.querySelector('.spinner');
  const text = btn.querySelector('.btn-text');
  btn.disabled = isLoading;
  if (spinner) spinner.classList.toggle('hidden', !isLoading);
  if (text) text.style.opacity = isLoading ? '0.7' : '1';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initial App Boot
document.addEventListener('DOMContentLoaded', () => {
  loadStatementsList();
});