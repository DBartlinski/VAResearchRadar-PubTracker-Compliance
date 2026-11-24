// Fiscal-year selection shared by every page. fiscal_years.js (written by build_static_dashboard_data.py)
// defines window.VARR_FYS = [{fy: 27, updated: "YYYY-MM-DD", ...}, ...], newest first.
(function () {
  const fys = (window.VARR_FYS || []).slice().sort((a, b) => b.fy - a.fy);
  const requested = Number(new URLSearchParams(location.search).get('fy'));
  const chosen = fys.find(f => f.fy === requested) || fys[0] || { fy: 26 };
  window.VARR_FY = chosen.fy;
  window.dataUrl = name => `./data/FY${chosen.fy}/${name}`;

  document.addEventListener('DOMContentLoaded', () => {
    const start = `Oct 1, ${2000 + chosen.fy - 1}`;
    const end = `Sep 30, ${2000 + chosen.fy}`;
    document.querySelectorAll('.fy-label').forEach(el => { el.textContent = `fiscal year ${2000 + chosen.fy}`; });
    document.querySelectorAll('.fy-range').forEach(el => { el.textContent = `${start} \u2013 ${end}`; });
    document.querySelectorAll('.fy-updated').forEach(el => { el.textContent = chosen.updated || ''; });

    const host = document.querySelector('.hero .container-fluid, header .container-fluid, h1');
    if (!host || fys.length < 2) return;
    const wrap = document.createElement('label');
    wrap.className = 'small ms-3 text-white';
    wrap.style.cssText = 'display:inline-flex;gap:.4rem;align-items:center;margin:.5rem 0';
    wrap.textContent = 'Fiscal year ';
    const select = document.createElement('select');
    select.className = 'form-select form-select-sm';
    select.style.width = 'auto';
    select.innerHTML = fys.map(f => `<option value="${f.fy}"${f.fy === chosen.fy ? ' selected' : ''}>FY${f.fy}</option>`).join('');
    select.addEventListener('change', () => {
      const url = new URL(location.href);
      url.searchParams.set('fy', select.value);
      location.href = url.toString();
    });
    wrap.appendChild(select);
    host.appendChild(wrap);
  });
})();
