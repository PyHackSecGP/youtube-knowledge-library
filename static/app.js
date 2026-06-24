/**
 * Toggle expand/collapse for queue items and library cards.
 * Pass the exact element ID to show/hide.
 */
function toggleExpand(id) {
  const el = document.getElementById(id);
  if (el) {
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
  }
}

const STATUS_LABELS = {
  pending:              'Pending...',
  fetching_transcript:  'Fetching transcript...',
  fetching_metadata:    'Fetching metadata...',
  summarizing:          'Summarizing...',
  done:                 'Done ✓',
  failed:               'Failed ✗',
  not_found:            'Not found',
};

/**
 * Poll /status/<job_id> every 2s for each job ID.
 * Updates DOM rows with current status. When all jobs reach a
 * terminal state (done/failed), shows the all-done banner.
 */
function startPolling(jobIds) {
  if (!jobIds || jobIds.length === 0) return;

  const terminal = new Set(['done', 'failed', 'not_found']);
  const settled = {};

  const interval = setInterval(async () => {
    for (const jobId of jobIds) {
      if (settled[jobId]) continue;

      try {
        const resp = await fetch('/status/' + jobId);
        const data = await resp.json();

        const row = document.querySelector('[data-job-id="' + jobId + '"]');
        if (row) {
          const urlEl = row.querySelector('.job-url');
          const statusEl = row.querySelector('.job-status');
          if (urlEl && data.url) urlEl.textContent = data.url;
          if (statusEl) {
            statusEl.textContent = STATUS_LABELS[data.status] || data.status;
            statusEl.style.color = data.status === 'done'   ? '#3fb950'
                                 : data.status === 'failed' ? '#f85149'
                                 : '#f0f6fc';
          }
        }

        if (terminal.has(data.status)) {
          settled[jobId] = true;
        }
      } catch (_) {
        // network error — keep polling
      }
    }

    const allSettled = jobIds.every(id => settled[id]);
    if (allSettled) {
      clearInterval(interval);
      const banner = document.getElementById('all-done');
      if (banner) banner.style.display = 'block';
    }
  }, 2000);
}
