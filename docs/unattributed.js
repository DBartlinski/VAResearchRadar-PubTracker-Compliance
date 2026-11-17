'use strict';

// Data from data/unattributed_va_funding.json (build_unattributed_funding_data.py).
(function () {
  const R = { ID: 0, DATE: 1, TITLE: 2, JOURNAL: 3, DOI: 4, PMID: 5, CAT: 6, PARTS: 7, FUNDERS: 8, GRANTS: 9, PT: 10, AWARDS: 11, PMC: 12, SOURCE: 13 };
  const MAX_ROWS = 500;
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let payload = null;
  let category = null;
  let shown = [];

  function linkList(r) {
    return [
      r[R.DOI] ? ['DOI', `https://doi.org/${r[R.DOI]}`] : null,
      r[R.PMID] ? ['PubMed', `https://pubmed.ncbi.nlm.nih.gov/${r[R.PMID]}/`] : null,
      r[R.PMC] ? ['PMC', `https://pmc.ncbi.nlm.nih.gov/articles/${r[R.PMC]}/`] : null,
      r[R.SOURCE] ? ['Source', r[R.SOURCE]] : null,
      /^pub\./.test(r[R.ID]) ? ['Dimensions', `https://va.dimensions.ai/details/publication/${r[R.ID]}`] : null,
    ].filter(Boolean);
  }

  // Full URL per link type, blank when the record has none.
  function linkCells(r) {
    const byName = Object.fromEntries(linkList(r));
    return ['DOI', 'PubMed', 'PMC', 'Source', 'Dimensions'].map(name => byName[name] || '');
  }

  function inPeriod() {
    const p = payload.periods[$('uaPeriod').value];
    return payload.records.filter(r => r[R.DATE] >= p.start && r[R.DATE] <= p.end);
  }

  function matches(r, ignoreCategory) {
    const part = $('uaParts').value;
    const pt = $('uaPt').value;
    const q = $('uaSearch').value.trim().toLowerCase();
    if (!ignoreCategory && category !== null && r[R.CAT] !== category) return false;
    if (part && !r[R.PARTS].split('; ').includes(part)) return false;
    if (pt !== '' && String(r[R.PT]) !== pt) return false;
    if (q && ![r[R.TITLE], r[R.JOURNAL], r[R.FUNDERS], r[R.GRANTS], r[R.AWARDS]].some(v => v.toLowerCase().includes(q))) return false;
    return true;
  }

  function render() {
    const records = inPeriod();
    const base = records.filter(r => matches(r, true));
    $('uaCards').innerHTML = payload.categories.map((name, i) => {
      const n = base.filter(r => r[R.CAT] === i).length;
      return `<div class="col-6 col-md-3"><div class="card card-cat text-center h-100 ${category === i ? 'active' : ''}" data-cat="${i}">
        <div class="card-body py-2"><div class="small text-muted">${esc(name)}</div><div class="fs-4 fw-semibold">${n.toLocaleString()}</div></div></div></div>`;
    }).join('');

    shown = records.filter(r => matches(r, false));
    $('uaCount').textContent = `${shown.length.toLocaleString()} of ${records.length.toLocaleString()} unattributed records` +
      (shown.length > MAX_ROWS ? ` (first ${MAX_ROWS} shown, CSV has all)` : '') + (category !== null ? ' - click the selected card again to clear' : '');
    $('uaRows').innerHTML = shown.slice(0, MAX_ROWS).map(r => {
      const links = linkList(r).map(([name, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener">${name}</a>`).join(' · ');
      return `<tr><td class="text-nowrap">${esc(r[R.DATE])}</td><td>${esc(r[R.TITLE])}</td><td>${esc(r[R.JOURNAL])}</td>
        <td>${esc(payload.categories[r[R.CAT]])}</td><td>${esc(r[R.PARTS])}</td><td>${esc(r[R.AWARDS])}</td><td>${esc(r[R.FUNDERS])}</td><td>${esc(r[R.GRANTS])}</td>
        <td>${r[R.PT] ? 'Yes' : 'No'}</td><td class="text-nowrap">${links}</td></tr>`;
    }).join('');
  }

  function download() {
    const header = ['Date', 'Title', 'Journal', 'VA funding', 'VA part', 'VA award codes', 'Funders', 'All grants', 'In PubTracker',
      'DOI Link', 'PubMed Link', 'PMC Link', 'Source Link', 'Dimensions Link', 'DOI', 'PubMed ID', 'Dimensions ID'];
    const rows = shown.map(r => [r[R.DATE], r[R.TITLE], r[R.JOURNAL], payload.categories[r[R.CAT]], r[R.PARTS], r[R.AWARDS], r[R.FUNDERS], r[R.GRANTS],
      r[R.PT] ? 'Yes' : 'No', ...linkCells(r), r[R.DOI], r[R.PMID], r[R.ID]]);
    const csv = [header, ...rows].map(row => row.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'unattributed_va_funding.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  async function init() {
    payload = await (await fetch('data/unattributed_va_funding.json')).json();
    $('uaPeriod').innerHTML = Object.keys(payload.periods).map(k => `<option>${esc(k)}</option>`).join('');
    const parts = [...new Set(payload.records.flatMap(r => r[R.PARTS] ? r[R.PARTS].split('; ') : []))].sort();
    $('uaParts').innerHTML = '<option value="">All</option>' + parts.map(p => `<option>${esc(p)}</option>`).join('');
    ['uaPeriod', 'uaParts', 'uaPt'].forEach(id => $(id).addEventListener('change', render));
    $('uaSearch').addEventListener('input', render);
    $('uaDownload').addEventListener('click', download);
    $('uaCards').addEventListener('click', e => {
      const card = e.target.closest('[data-cat]');
      if (!card) return;
      const i = Number(card.dataset.cat);
      category = category === i ? null : i;
      render();
    });
    render();
  }

  init().catch(err => { $('uaCount').textContent = `Failed to load data: ${err.message}`; });
})();
