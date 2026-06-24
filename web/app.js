'use strict';

/* ============ 工具 ============ */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const fmt = (n) => (n == null ? '—' : Math.round(n).toLocaleString('en-US'));
const fmtSigned = (n) => (n == null ? '—' : (n >= 0 ? '+' : '') + Math.round(n).toLocaleString('en-US'));
const pct = (n) => (n == null ? '—' : n.toFixed(2) + '%');
// 1 張 = 1000 股；持有股數一律以「張」顯示
const toLots = (shares) => (shares == null ? null : shares / 1000);
const fmtLots = (shares) => {
  const l = toLots(shares);
  if (l == null) return '—';
  return (Number.isInteger(l) ? l : +l.toFixed(1)).toLocaleString('en-US');
};
const fmtSignedLots = (shares) => {
  const l = toLots(shares);
  if (l == null) return '—';
  const v = Number.isInteger(l) ? l : +l.toFixed(1);
  return (v >= 0 ? '+' : '') + v.toLocaleString('en-US');
};

// 異動類型 → 樣式類別（台股：紅=加碼/漲、綠=減碼/跌）
const TYPE_CLASS = { '加碼': 'up', '新增持股': 'new', '減碼': 'down', '出清持股': 'out' };
const CSS = getComputedStyle(document.documentElement);
const COLOR = {
  up: CSS.getPropertyValue('--up').trim(),
  down: CSS.getPropertyValue('--down').trim(),
  new: CSS.getPropertyValue('--new').trim(),
  out: CSS.getPropertyValue('--out').trim(),
  gold: CSS.getPropertyValue('--gold').trim(),
  ink: CSS.getPropertyValue('--ink').trim(),
  dim: CSS.getPropertyValue('--ink-dim').trim(),
  panel: CSS.getPropertyValue('--panel-2').trim(),
  line: CSS.getPropertyValue('--line').trim(),
};
const typeColor = (t) => COLOR[TYPE_CLASS[t]] || COLOR.dim;

let DATA = null;
let weightChart = null, commonChart = null;
let commonBarIndex = {};
const state = { detailCode: null, diffFilter: 'all', sortKey: 'weight_pct', sortDir: -1, commonDir: 'add' };

/* ============ 啟動 ============ */
init();
async function init() {
  try {
    const res = await fetch('data.json', { cache: 'no-store' });
    DATA = await res.json();
  } catch (e) {
    document.body.innerHTML = '<p style="padding:40px;color:#9aa6b8;font-family:sans-serif">無法載入 data.json，請先執行：<code>python -m active_etf_tracker.cli dashboard</code>，並以 <code>--serve</code> 或本機伺服器開啟此頁。</p>';
    return;
  }
  renderTop();
  setupTabs();
  renderOverview();
  setupDetail();
  setupCommon();
  setupRefresh();
  window.addEventListener('resize', () => { weightChart && weightChart.resize(); commonChart && commonChart.resize(); });
}

/* ============ 頂部 KPI ============ */
function renderTop() {
  const s = DATA.summary;
  $$('[data-kpi]').forEach(el => countUp(el, s[el.dataset.kpi] ?? 0));
  const t = (DATA.generated_at || '').replace('T', ' ').slice(0, 16);
  $('#gen-time').textContent = t || '—';
  const tf = $('#gen-time-foot');
  if (tf) tf.textContent = t || '—';
}
function countUp(el, target) {
  const dur = 700, start = performance.now();
  const tick = (now) => {
    const p = Math.min(1, (now - start) / dur);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(target * e).toLocaleString('en-US');
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ============ 分頁切換 ============ */
function setupTabs() {
  $$('.tab').forEach(btn => btn.addEventListener('click', () => {
    $$('.tab').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    $$('.view').forEach(v => v.classList.remove('is-active'));
    $('#view-' + btn.dataset.view).classList.add('is-active');
    if (btn.dataset.view === 'detail' && weightChart) weightChart.resize();
    if (btn.dataset.view === 'common') { renderCommon(); commonChart && commonChart.resize(); }
  }));
}

/* ============ 1. 總覽 ============ */
function renderOverview(filter = '') {
  const grid = $('#etf-grid');
  const f = filter.trim().toLowerCase();
  const list = DATA.etfs.filter(e =>
    !f || e.etf_code.toLowerCase().includes(f) || (e.etf_name || '').toLowerCase().includes(f) || (e.issuer || '').toLowerCase().includes(f));
  if (!list.length) { grid.innerHTML = '<p class="empty">查無符合的 ETF</p>'; return; }
  grid.innerHTML = list.map(e => {
    const d = DATA.diffs[e.etf_code];
    const diffN = d ? d.items.length : 0;
    return `<div class="etf-card" data-code="${e.etf_code}">
      <div class="ec-top">
        <span class="ec-code">${e.etf_code}</span>
        <span class="ec-badge stock">${e.etf_type === 'stock' ? '股票型' : e.etf_type || '—'}</span>
      </div>
      <div class="ec-name">${e.etf_name || ''}</div>
      <div class="ec-stats">
        <div class="ec-stat"><div class="v">${e.holding_count}</div><div class="l">持股檔數</div></div>
        <div class="ec-stat"><div class="v" style="font-size:13px">${e.latest_date}</div><div class="l">資料日期</div></div>
        <div class="ec-stat ec-diff"><div class="v">${diffN || '—'}</div><div class="l">當日異動</div></div>
      </div>
    </div>`;
  }).join('');
  $$('.etf-card', grid).forEach(c => c.addEventListener('click', () => openDetail(c.dataset.code)));
}
$('#etf-search').addEventListener('input', (e) => renderOverview(e.target.value));

/* ============ 2. 單檔 ============ */
function setupDetail() {
  const sel = $('#etf-select');
  sel.innerHTML = DATA.etfs.map(e => `<option value="${e.etf_code}">${e.etf_code}　${e.etf_name || ''}</option>`).join('');
  sel.addEventListener('change', () => openDetail(sel.value, false));
  weightChart = echarts.init($('#weight-chart'), null, { renderer: 'canvas' });
  weightChart.on('click', (p) => { if (p.data && p.data.sid) highlightRow(p.data.sid); });
  if (DATA.etfs.length) openDetail(DATA.etfs[0].etf_code, false);
}
function openDetail(code, switchTab = true) {
  state.detailCode = code;
  $('#etf-select').value = code;
  if (switchTab) $('.tab[data-view="detail"]').click();
  const e = DATA.etfs.find(x => x.etf_code === code);
  const h = DATA.holdings[code], d = DATA.diffs[code];
  // meta
  $('#detail-meta').innerHTML = `
    <div class="dm"><span class="v">${h.data_date}</span><span class="l">資料日期</span></div>
    <div class="dm"><span class="v">${e.holding_count}</span><span class="l">持股檔數</span></div>
    <div class="dm"><span class="v">${d ? d.items.length : '—'}</span><span class="l">當日異動</span></div>
    <div class="dm"><span class="v" style="font-size:13px">${e.issuer || '—'}</span><span class="l">投信</span></div>`;
  $('#diff-date').textContent = d ? `${d.from_date} → ${d.to_date}` : '尚無前一日可比對';
  $('#holding-count').textContent = `共 ${h.items.length} 檔`;
  renderWeightChart(h);
  renderDiffFilter(d);
  renderDiffList(d);
  renderHoldingsTable(h, d);
}

function renderWeightChart(h) {
  const top = [...h.items].filter(x => x.weight_pct).sort((a, b) => b.weight_pct - a.weight_pct).slice(0, 15);
  const others = h.items.reduce((s, x) => s + (x.weight_pct || 0), 0) - top.reduce((s, x) => s + x.weight_pct, 0);
  const data = top.map((x, i) => ({
    name: x.stock_name, value: x.weight_pct, sid: x.stock_id,
    itemStyle: { color: shade(i, top.length) },
  }));
  if (others > 0.05) data.push({ name: '其他', value: +others.toFixed(2), sid: null, itemStyle: { color: COLOR.line } });
  // 甜甜圈本身不畫外部標籤（名稱長、數量多會擠爆/被裁切），名稱全部放到右側圖例清單
  weightChart.setOption({
    tooltip: {
      trigger: 'item', backgroundColor: COLOR.panel, borderColor: COLOR.line, textStyle: { color: COLOR.ink },
      formatter: (p) => `${p.data.sid ? p.data.sid + ' ' : ''}${p.name}<br/><b>${pct(p.value)}</b>（占圖 ${p.percent}%）`,
    },
    series: [{
      type: 'pie', radius: ['46%', '76%'], center: ['50%', '50%'],
      itemStyle: { borderColor: CSS.getPropertyValue('--panel').trim(), borderWidth: 2 },
      label: { show: false },
      labelLine: { show: false },
      emphasis: { scale: true, scaleSize: 6, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,.4)' } },
      data,
    }],
  }, true);
  // 點扇形 → 定位表格
  weightChart.off('click');
  weightChart.on('click', (p) => { if (p.data && p.data.sid) highlightRow(p.data.sid); highlightLegend(p.dataIndex); });

  // 右側圖例清單：色塊 + 名稱(可省略號) + 代號 + 權重；懸停高亮對應扇形
  const legend = $('#weight-legend');
  legend.innerHTML = data.map((d, i) => `
    <div class="wl-row" data-i="${i}" data-sid="${d.sid || ''}" title="${d.name}${d.sid ? ' (' + d.sid + ')' : ''}　${pct(d.value)}">
      <span class="wl-rank">${d.sid ? i + 1 : ''}</span>
      <span class="wl-sw" style="background:${d.itemStyle.color}"></span>
      <span class="wl-name">${d.name}</span>
      <span class="wl-code">${d.sid || ''}</span>
      <span class="wl-pct">${d.value.toFixed(2)}%</span>
    </div>`).join('');
  $$('.wl-row', legend).forEach(row => {
    const i = +row.dataset.i;
    row.addEventListener('mouseenter', () => weightChart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: i }));
    row.addEventListener('mouseleave', () => weightChart.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex: i }));
    row.addEventListener('click', () => { if (row.dataset.sid) highlightRow(row.dataset.sid); });
  });
}
function highlightLegend(i) {
  const rows = $$('#weight-legend .wl-row');
  rows.forEach(r => r.classList.remove('hot'));
  const el = rows.find(r => +r.dataset.i === i);
  if (el) { el.classList.add('hot'); el.scrollIntoView({ block: 'nearest' }); }
}
function shade(i, n) {
  // 金→藍漸層
  const t = i / Math.max(1, n - 1);
  const a = [231, 185, 78], b = [91, 140, 255];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function renderDiffFilter(d) {
  const wrap = $('#diff-filter');
  if (!d || !d.items.length) { wrap.innerHTML = ''; return; }
  const counts = {};
  d.items.forEach(x => counts[x.change_type] = (counts[x.change_type] || 0) + 1);
  const order = ['加碼', '新增持股', '減碼', '出清持股'];
  state.diffFilter = 'all';
  wrap.innerHTML = `<span class="chip all is-active" data-k="all">全部 ${d.items.length}</span>` +
    order.filter(k => counts[k]).map(k => `<span class="chip" data-k="${k}">${k} ${counts[k]}</span>`).join('');
  $$('.chip', wrap).forEach(c => c.addEventListener('click', () => {
    $$('.chip', wrap).forEach(x => x.classList.remove('is-active'));
    c.classList.add('is-active');
    state.diffFilter = c.dataset.k;
    renderDiffList(d);
  }));
}
function renderDiffList(d) {
  const wrap = $('#diff-list');
  if (!d || !d.items.length) { wrap.innerHTML = '<p class="empty">此 ETF 尚無第二個資料日期，明日再抓即可比對。</p>'; return; }
  let items = d.items.slice();
  if (state.diffFilter !== 'all') items = items.filter(x => x.change_type === state.diffFilter);
  items.sort((a, b) => Math.abs(b.shares_diff || 0) - Math.abs(a.shares_diff || 0));
  wrap.innerHTML = items.map(x => {
    const cl = TYPE_CLASS[x.change_type];
    const up = (x.shares_diff || 0) >= 0;
    return `<div class="diff-row ${cl}" data-sid="${x.stock_id}">
      <div class="dr-name"><div class="n">${x.stock_name || ''}</div><div class="c">${x.stock_id}</div></div>
      <span class="dr-tag ${cl}">${x.change_type}</span>
      <div class="dr-val ${up ? 'up' : 'down'}">${fmtSignedLots(x.shares_diff)} 張<br><span style="font-size:10px;color:var(--ink-faint)">${x.weight_diff_pct != null ? (x.weight_diff_pct >= 0 ? '+' : '') + x.weight_diff_pct + '%' : ''}</span></div>
    </div>`;
  }).join('') || '<p class="empty">無此類異動</p>';
}

function renderHoldingsTable(h, d) {
  const diffMap = {};
  if (d) d.items.forEach(x => diffMap[x.stock_id] = x);
  const rows = h.items.map((x, i) => ({ ...x, idx: i + 1, ...mergeDiff(diffMap[x.stock_id]) }));
  state._rows = rows;
  sortAndRenderTable();
  $$('#holdings-table th.sortable').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.sort;
      state.sortDir = (state.sortKey === k) ? -state.sortDir : -1;
      state.sortKey = k;
      sortAndRenderTable();
    };
  });
}
function mergeDiff(x) {
  if (!x) return { change_type: null, shares_diff: null };
  return { change_type: x.change_type, shares_diff: x.shares_diff };
}
function sortAndRenderTable() {
  const tb = $('#holdings-table tbody');
  const k = state.sortKey, dir = state.sortDir;
  const rows = [...state._rows].sort((a, b) => {
    const av = a[k] ?? -Infinity, bv = b[k] ?? -Infinity;
    if (typeof av === 'string') return dir * av.localeCompare(bv);
    return dir * (av - bv);
  });
  $$('#holdings-table th').forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
  const th = $(`#holdings-table th[data-sort="${k}"]`);
  if (th) th.classList.add(dir > 0 ? 'sort-asc' : 'sort-desc');
  tb.innerHTML = rows.map(r => {
    const tag = r.change_type
      ? `<span class="mini-tag ${TYPE_CLASS[r.change_type]}">${r.change_type}</span>`
      : '<span class="mini-tag flat">—</span>';
    const sd = r.shares_diff != null
      ? `<span class="${r.shares_diff >= 0 ? 'cell-up' : 'cell-down'}">${fmtSignedLots(r.shares_diff)}</span>` : '—';
    return `<tr data-sid="${r.stock_id}">
      <td class="num">${r.idx}</td>
      <td class="num">${r.stock_id}</td>
      <td>${r.stock_name || ''}</td>
      <td class="num">${r.weight_pct != null ? r.weight_pct.toFixed(2) : '—'}</td>
      <td class="num">${fmtLots(r.shares)}</td>
      <td class="num">${sd}</td>
      <td>${tag}</td>
    </tr>`;
  }).join('');
}
function highlightRow(sid) {
  const tr = $(`#holdings-table tr[data-sid="${sid}"]`);
  if (tr) { tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
    tr.style.transition = 'background .2s'; tr.style.background = 'rgba(231,185,78,.18)';
    setTimeout(() => tr.style.background = '', 1100); }
}

/* ============ 3. 共同榜 ============ */
function setupCommon() {
  commonChart = echarts.init($('#common-chart'), null, { renderer: 'canvas' });
  commonChart.on('click', (p) => { const el = $(`.cm-row[data-sid="${p.data.sid}"]`); if (el) flashRow(el); });
  $$('#common-toggle .seg-btn').forEach(b => b.addEventListener('click', () => {
    $$('#common-toggle .seg-btn').forEach(x => x.classList.remove('is-active'));
    b.classList.add('is-active');
    state.commonDir = b.dataset.dir;
    $('#common-toggle').dataset.dir = b.dataset.dir;
    renderCommon();
  }));
}
function renderCommon() {
  const add = state.commonDir === 'add';
  const list = (add ? DATA.common_add : DATA.common_reduce).slice(0, 30);
  $('#common-title').textContent = add ? '共同加碼排行' : '共同減碼排行';
  const color = add ? COLOR.up : COLOR.down;
  // 圖（橫向長條，前 18）
  const top = list.slice(0, 18).reverse();
  // sid → 長條 dataIndex（供點列高亮）
  commonBarIndex = {};
  top.forEach((x, i) => { commonBarIndex[x.stock_id] = i; });
  commonChart.setOption({
    grid: { left: 95, right: 64, top: 12, bottom: 12 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: COLOR.panel, borderColor: COLOR.line, textStyle: { color: COLOR.ink },
      formatter: (ps) => { const p = ps[0]; return `${p.data.sid} ${p.name}<br/>同向 <b>${p.value}</b> 檔<br/>張數合計 ${fmtSignedLots(p.data.tot)} 張`; } },
    xAxis: { type: 'value', axisLabel: { color: COLOR.dim }, splitLine: { lineStyle: { color: COLOR.line } } },
    yAxis: { type: 'category', data: top.map(x => x.stock_name), axisLabel: { color: COLOR.dim, fontSize: 11 }, axisLine: { lineStyle: { color: COLOR.line } } },
    series: [{
      type: 'bar', barWidth: '62%',
      emphasis: { itemStyle: { color: COLOR.gold, borderColor: COLOR.ink, borderWidth: 1 } },
      data: top.map(x => ({ value: x.etf_count, sid: x.stock_id, tot: x.total_shares_diff,
        itemStyle: { color, borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: 'right', color: COLOR.ink, fontFamily: 'monospace', formatter: '{c} 檔' },
    }],
  }, true);
  // 清單
  $('#common-list').innerHTML = list.map((x, i) => `
    <div class="cm-row" data-sid="${x.stock_id}">
      <span class="cm-rank">${i + 1}</span>
      <div class="cm-main"><div class="n">${x.stock_name || ''} <span style="color:var(--ink-faint);font-family:var(--mono);font-size:11px">${x.stock_id}</span></div>
        <div class="codes">${x.etf_codes.join(' · ')}</div></div>
      <div class="cm-count ${add ? 'up' : 'down'}">${x.etf_count}<small> 檔</small></div>
    </div>`).join('') || '<p class="empty">無共同操作（需多檔 ETF 皆有兩個資料日期）</p>';
  $$('.cm-row').forEach(r => r.addEventListener('click', () => {
    flashRow(r);
    highlightBar(r.dataset.sid);
  }));
}
function flashRow(el) {
  $$('.cm-row').forEach(r => r.classList.remove('hot'));
  el.classList.add('hot'); el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

/* ============ 更新資料按鈕（需 dashboard --serve 後端；靜態部署自動隱藏） ============ */
const refreshBtn = $('#refresh-btn');
let cooldownTimer = null, pollTimer = null;

async function setupRefresh() {
  let st;
  try {
    const r = await fetch('api/status', { cache: 'no-store' });
    if (!r.ok) return;                 // 無後端（如 GitHub Pages 靜態）→ 按鈕保持隱藏
    st = await r.json();
  } catch (e) { return; }
  refreshBtn.hidden = false;
  refreshBtn.addEventListener('click', onRefreshClick);
  applyStatus(st);
}
function applyStatus(st) {
  if (st.running) { enterRunning(); startPolling(); }
  else if (st.cooldown_remaining > 0) { startCooldown(st.cooldown_remaining); }
  else setReady();
}
function setLabel(t) { $('.rb-label', refreshBtn).textContent = t; }
function mmss(s) { const m = Math.floor(s / 60), x = s % 60; return `${m}:${String(x).padStart(2, '0')}`; }
function setReady() {
  clearInterval(cooldownTimer); cooldownTimer = null;
  refreshBtn.disabled = false; refreshBtn.classList.remove('is-running', 'is-cooldown');
  setLabel('更新資料');
}
function enterRunning() {
  refreshBtn.disabled = true; refreshBtn.classList.add('is-running'); refreshBtn.classList.remove('is-cooldown');
  setLabel('更新中…');
}
function startCooldown(sec) {
  refreshBtn.disabled = true; refreshBtn.classList.add('is-cooldown'); refreshBtn.classList.remove('is-running');
  clearInterval(cooldownTimer);
  let rem = sec;
  const tick = () => {
    if (rem <= 0) { setReady(); return; }
    setLabel('可更新 ' + mmss(rem)); rem--;
  };
  tick(); cooldownTimer = setInterval(tick, 1000);
}
async function onRefreshClick() {
  try {
    const res = await fetch('api/update', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (res.status === 202) { enterRunning(); startPolling(); toast('已開始更新，約需數分鐘，完成後會自動刷新'); }
    else if (res.status === 429) { startCooldown(data.remaining || 1800); toast(data.message || '冷卻中，請稍候'); }
    else if (res.status === 409) { enterRunning(); startPolling(); toast('更新進行中…'); }
    else toast('更新失敗，請看伺服器訊息');
  } catch (e) { toast('無法連線到更新服務'); }
}
function startPolling() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    let st;
    try { const r = await fetch('api/status', { cache: 'no-store' }); st = await r.json(); }
    catch (e) { return; }
    if (!st.running) {
      clearInterval(pollTimer); pollTimer = null;
      await refreshData();
      toast(st.last_error ? '更新完成，但有狀況請看伺服器紀錄' : '更新完成 ✓');
      startCooldown(st.cooldown_remaining > 0 ? st.cooldown_remaining : 1);
    }
  }, 4000);
}
async function refreshData() {
  try {
    const r = await fetch('data.json?t=' + Date.now(), { cache: 'no-store' });
    DATA = await r.json();
  } catch (e) { return; }
  renderTop();
  $('#etf-select').innerHTML = DATA.etfs.map(e => `<option value="${e.etf_code}">${e.etf_code}　${e.etf_name || ''}</option>`).join('');
  renderOverview($('#etf-search').value || '');
  if (state.detailCode && DATA.holdings[state.detailCode]) openDetail(state.detailCode, false);
  else if (DATA.etfs.length) openDetail(DATA.etfs[0].etf_code, false);
  renderCommon();
}
function toast(msg) {
  let t = $('#toast');
  if (!t) { t = document.createElement('div'); t.id = 'toast'; document.body.appendChild(t); }
  t.textContent = msg; t.className = 'show';
  clearTimeout(t._h); t._h = setTimeout(() => { t.className = ''; }, 3400);
}
// 點清單列 → 高亮圖上對應長條（僅前 18 名有長條）
function highlightBar(sid) {
  if (!commonChart) return;
  commonChart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
  const di = commonBarIndex[sid];
  if (di != null) {
    commonChart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: di });
    commonChart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: di });
  } else {
    commonChart.dispatchAction({ type: 'hideTip' });
  }
}
