'use strict';
/* Quant Dashboard front end. Vanilla JS, no build step. Read-only: no action buttons, ever.
   Structure: utils + fmt -> Panel scheduler (setTimeout chains, AbortController 8 s) -> chart helpers
   (Chart.js 4 when loaded, inline canvas fallback otherwise) -> one render function per panel -> keyboard/init. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const ET = 'America/New_York';
const UNIVERSE = ['NVDA', 'TSLA', 'AAPL', 'MSFT', 'META', 'AMD', 'AMZN', 'GOOGL', 'AVGO', 'NFLX', 'SOXL', 'SOXS', 'PLTR', 'MSTR', 'COIN', 'SMCI'];
const DAILY_UNI = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'TLT', 'GLD', 'UPRO', 'TQQQ', 'TMF'];
const RED_EVENTS = new Set(['order_dead', 'step_error', 'decide_error', 'feed_error', 'disconnected', 'loss_limit', 'halt', 'preflight_failed', 'stale_book', 'ignored_book_file', 'refused', 'flatten', 'connect_failed', 'not_started', 'flatten_from_account', 'foreign_positions_ignored']);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ls = { get(k, d) { try { const v = localStorage.getItem('qd.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('qd.' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } } };
const isNum = x => typeof x === 'number' && Number.isFinite(x);
const num = x => { if (isNum(x)) return x; if (typeof x !== 'string') return null; const v = parseFloat(x.replace(/[$,%\s]/g, '')); return Number.isFinite(v) ? v : null; };
const sum = (a, f) => a.reduce((t, x) => { const v = f(x); return isNum(v) ? t + v : t; }, 0);

/* ---- time: every timestamp is shown in ET, the ISO string sits in the title attribute ---- */
const dtf = {};
function etParts(ms) { // {y,m,d,h,mi,s,wd} of an instant in ET
  const f = dtf.p || (dtf.p = new Intl.DateTimeFormat('en-US', { timeZone: ET, hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short' }));
  const o = {}; for (const p of f.formatToParts(new Date(ms))) o[p.type] = p.value;
  return { y: +o.year, m: +o.month, d: +o.day, h: +o.hour % 24, mi: +o.minute, s: +o.second, wd: o.weekday };
}
const parseTs = s => { if (!s) return NaN; if (isNum(s)) return s; const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(s);
  return m ? Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : Date.parse(String(s).replace(' ', 'T')); };
const pad = n => String(n).padStart(2, '0');
const etDateStr = ms => { const p = etParts(ms); return `${p.y}-${pad(p.m)}-${pad(p.d)}`; };
const todayET = () => etDateStr(Date.now());
function etToMs(dateStr, h, mi) { // instant of an ET wall-clock time on a date (one DST correction pass)
  const [y, m, d] = dateStr.split('-').map(Number); let g = Date.UTC(y, m - 1, d, h, mi); const p = etParts(g);
  return g - (((p.d - d) * 1440 + (p.h - h) * 60 + (p.mi - mi)) * 60000);
}
const etMinute = ms => { const p = etParts(ms); return p.h * 60 + p.mi; };
const fmt = {
  none: '<span class="mut">—</span>',
  fix: (x, d) => x.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }),
  money(x, signed) { if (!isNum(x)) return fmt.none; const s = fmt.fix(Math.abs(x), Math.abs(x) >= 1000 ? 0 : 2); return (x < 0 ? '-' : signed && x > 0 ? '+' : '') + s; },
  px: x => isNum(x) ? fmt.fix(x, Math.abs(x) < 1 ? 4 : 2) : fmt.none,
  n2: x => isNum(x) ? fmt.fix(x, 2) : fmt.none,
  int: x => isNum(x) ? fmt.fix(Math.round(x), 0) : fmt.none,
  pct(x, signed = true) { if (!isNum(x)) return fmt.none; const v = x * 100; return (v < 0 ? '-' : signed && v > 0 ? '+' : '') + fmt.fix(Math.abs(v), 2) + '%'; },
  sign: x => isNum(x) ? (x > 0 ? 'pos' : x < 0 ? 'neg' : 'mut') : 'mut',
  pnl: x => `<span class="${fmt.sign(x)}">${fmt.money(x, true)}</span>`,
  et(ts, sec = true) { const ms = parseTs(ts); if (!isNum(ms)) return '—'; const p = etParts(ms); return `${pad(p.h)}:${pad(p.mi)}` + (sec ? `:${pad(p.s)}` : ''); },
  etT: (ts, sec) => ts ? `<span title="${esc(ts)}">${fmt.et(ts, sec)}</span>` : fmt.none,
  etD(ts) { const ms = parseTs(ts); return isNum(ms) ? `${etDateStr(ms)} ${fmt.et(ms)}` : '—'; },
  age(s) { if (!isNum(s)) return '—'; s = Math.max(0, Math.round(s)); if (s < 60) return s + 's'; if (s < 3600) return Math.floor(s / 60) + 'm ' + pad(s % 60) + 's'; if (s < 86400) return Math.floor(s / 3600) + 'h ' + pad(Math.floor(s % 3600 / 60)) + 'm'; return Math.floor(s / 86400) + 'd ' + (Math.floor(s % 86400 / 3600)) + 'h'; },
  ageOf: ts => { const ms = parseTs(ts); return isNum(ms) ? fmt.age((serverNowMs() - ms) / 1000) : '—'; },
  dur: ms => isNum(ms) ? `${Math.floor(ms / 60000)}:${pad(Math.floor(ms / 1000) % 60)}` : '—',
  trunc: (s, n) => { s = String(s == null ? '' : s); return s.length > n ? `<span title="${esc(s)}">${esc(s.slice(0, n))}…</span>` : esc(s); },
};
const pill = (cls, text, title) => `<span class="pill ${cls}"${title ? ` title="${esc(title)}"` : ''}>${esc(text)}</span>`;
const chip = (text, cls = '', attrs = '') => `<span class="chip ${cls}" ${attrs}>${esc(text)}</span>`;
const symChip = (s, lit) => chip(s, lit ? 'lit' : '', `data-sym="${esc(s)}"`);
const stat = (k, v) => `<span class="stat"><b>${esc(k)}</b>${v}</span>`;
function wbar(label, w, cur, hollow) { // horizontal weight bar: negative to the left, red; optional current-weight underline
  const pct = Math.min(50, Math.abs(w || 0) * 50 / 1.6), neg = (w || 0) < 0;
  const cw = isNum(cur) ? Math.min(50, Math.abs(cur) * 50 / 1.6) : 0;
  return `<div class="wb${hollow ? ' hollow' : ''}"><span class="k sym" data-sym="${esc(label)}">${esc(label)}</span><div class="track">` +
    `<i class="fill${neg ? ' neg' : ''}" style="${neg ? 'right' : 'left'}:50%;width:${pct}%"></i>` +
    (isNum(cur) ? `<i class="fill cur" style="${cur < 0 ? 'right' : 'left'}:50%;width:${cw}%"></i>` : '') +
    `</div><span class="val">${fmt.n2(w)}${isNum(cur) ? ` <span class="mut">cur ${fmt.n2(cur)}</span>` : ''}</span></div>`;
}
function setBody(tableId, rows, emptyText) { // reuse the <tbody> node: replace innerHTML, no accumulating listeners
  const tb = $('#' + tableId + ' tbody'); if (!tb) return;
  tb.innerHTML = rows.length ? rows.join('') : `<tr><td colspan="20" class="empty">${esc(emptyText || 'none')}</td></tr>`;
}
const tr = (cells, cls = '', attrs = '') => `<tr class="${cls}" ${attrs}>${cells.map(c => `<td class="${c && c.r ? 'r' : ''}">${c && c.r ? c.h : (c == null ? fmt.none : c)}</td>`).join('')}</tr>`;
const R = h => ({ r: true, h });

/* ---- store: cross-panel state ---- */
const store = { sym: ls.get('sym', 'NVDA'), date: todayET(), navDays: 1, paused: false, pausedAt: 0, statusFails: 0, unreachableSince: null,
  uni: new Set(UNIVERSE), duni: new Set(DAILY_UNI), status: null, account: null, intraday: null, daily: null, nav: null, summary: null,
  acks: ls.get('acks', {}), ledger: null, ledgerKey: '', ledgerSort: { key: 'ts', dir: -1 }, ledgerTrack: 'all', ledgerCommit: '', logsOpened: false, chartRetries: 0 };
const sleeveOf = s => store.uni.has(s) ? 'intraday' : store.duni.has(s) ? 'daily' : 'other';

/* ---- scheduler ---- */
const panels = {};
let skewMs = 0; // server_now - client clock, from the newest response
const serverNowMs = () => Date.now() + skewMs;
class Panel {
  constructor(id, sel, endpoint, intervalMs, render) {
    Object.assign(this, { id, endpoint, intervalMs, render, el: $(sel), lastData: null, lastGood: null, receivedAt: 0, asOfMs: 0, serverNowMs: 0, errorSince: null, lastGoodAt: null, errorMsg: '', timer: null, ctrl: null, nextOverride: null });
    if (!this.el) throw new Error('panel element missing: ' + sel);
    if (this.el.classList.contains('pb') || this.el.querySelector('.pb')) this.el.classList.add('skel');
    panels[id] = this;
  }
  url() { return typeof this.endpoint === 'function' ? this.endpoint() : this.endpoint; }
  base() { const v = typeof this.intervalMs === 'function' ? this.intervalMs() : this.intervalMs; return v || 60000; }
  interval() { return document.hidden ? this.base() * 6 : this.base(); }
  schedule(ms) { clearTimeout(this.timer); this.timer = setTimeout(() => this.tick(), ms); }
  refresh() { this.tick(true); }
  async tick(force) {
    if (store.paused && !force) return this.schedule(1000);
    const url = this.url(); if (!url) return this.schedule(this.interval());
    if (this.ctrl) this.ctrl.abort();
    const ctrl = this.ctrl = new AbortController(); const to = setTimeout(() => { ctrl.timedOut = true; ctrl.abort(); }, 8000);
    try {
      const res = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      this.receivedAt = performance.now(); this.serverNowMs = parseTs(data.server_now) || Date.now(); this.asOfMs = parseTs(data.as_of) || this.serverNowMs;
      if (data.server_now) skewMs = this.serverNowMs - Date.now();
      this.lastData = data;
      if (data.error) { this.fail(String(data.error)); if (!this.lastGood) this.safeRender(data); }
      else { this.errorSince = null; this.lastGoodAt = Date.now(); this.lastGood = data; this.safeRender(data); }
      this.flashDot(); this.el.classList.remove('skel');
      if (this.id === 'status') { store.statusFails = 0; store.unreachableSince = null; $('#apistrip').hidden = true; }
    } catch (e) {
      if (ctrl.signal.aborted && !ctrl.timedOut) { /* superseded by a forced refresh */ } else this.fail(ctrl.timedOut ? 'timeout (8 s)' : (e.message || String(e)));
      if (this.id === 'status' && (!ctrl.signal.aborted || ctrl.timedOut) && ++store.statusFails >= 2) {
        store.unreachableSince = store.unreachableSince || Date.now(); const s = $('#apistrip'); s.hidden = false;
        s.textContent = `dashboard server unreachable since ${fmt.et(store.unreachableSince)} ET`; this.nextOverride = store.statusFails > 4 ? 30000 : 10000;
      }
    } finally {
      clearTimeout(to);
      if (this.ctrl === ctrl) { this.ctrl = null; this.showErr(); this.schedule(this.nextOverride != null ? this.nextOverride : this.interval()); this.nextOverride = null; }
    }
  }
  safeRender(d) { try { this.render(d, this); } catch (e) { console.error(this.id, e); this.fail('render: ' + e.message); } }
  fail(msg) { if (!this.errorSince) this.errorSince = Date.now(); this.errorMsg = msg; }
  showErr() {
    const e = this.el.querySelector('[data-err]'); if (!e) return;
    this.el.classList.toggle('haserr', !!this.errorSince); e.hidden = !this.errorSince; if (!this.errorSince) return;
    const m = this.errorMsg || 'error';
    e.innerHTML = `<span title="${esc(m)}">${esc(m.slice(0, 160))}</span> · since ${fmt.et(this.errorSince)} · last good ${this.lastGoodAt ? fmt.et(this.lastGoodAt) : '—'}<a data-retry="${this.id}">retry</a>`;
  }
  flashDot() { const d = this.el.querySelector('[data-dot]'); if (d) { d.classList.remove('on'); void d.offsetWidth; d.classList.add('on'); } }
  ageS() { return this.receivedAt ? (this.serverNowMs - this.asOfMs) / 1000 + (performance.now() - this.receivedAt) / 1000 : null; }
}
function tickStamps() { // one global 1 Hz interval: clock, phase, panel age stamps, paused badge
  const now = serverNowMs(), p = etParts(now); $('#clock').textContent = `${pad(p.h)}:${pad(p.mi)}:${pad(p.s)} ET`;
  const m = p.h * 60 + p.mi, ph = $('#phase'), wk = p.wd === 'Sat' || p.wd === 'Sun';
  const [pc, pt] = wk ? ['off', 'WEEKEND'] : m >= 570 && m < 960 ? ['ok', 'RTH'] : m >= 240 && m < 570 ? ['warn', 'PRE'] : m >= 960 && m < 1200 ? ['warn', 'AFTER'] : ['off', 'CLOSED'];
  ph.className = 'pill ' + pc; ph.textContent = pt;
  let worst = 0;
  for (const pn of Object.values(panels)) {
    const el = pn.el.querySelector('[data-asof]'), a = pn.ageS(); if (!el || a == null) continue;
    const iv = pn.base() / 1000, lvl = a > 5 * iv ? 2 : a > 2 * iv ? 1 : 0; worst = Math.max(worst, lvl);
    el.className = 'asof ' + ['', 'amber', 'red'][lvl]; el.textContent = (lvl ? 'STALE ' : '') + 'as of ' + fmt.age(a) + ' ago';
    el.title = 'as_of ' + new Date(pn.asOfMs).toISOString(); pn.el.classList.toggle('stale5', lvl === 2);
  }
  $('#worst').className = 'worst ' + ['', 'amber', 'red'][worst];
  const pb = $('#paused'); pb.hidden = !store.paused; if (store.paused) pb.textContent = 'PAUSED ' + fmt.dur(Date.now() - store.pausedAt);
}
const refreshAll = () => Object.values(panels).forEach(p => p.refresh());

/* ---- charts: Chart.js when loaded, inline canvas fallback otherwise ---- */
const charts = {}, MONO = '"JetBrains Mono","Cascadia Mono",Consolas,monospace';
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function offlineTag(panelId, on) { const h = $('#p-' + panelId + ' .ph'); if (!h) return; let t = h.querySelector('.offline'); if (on && !t) { t = document.createElement('span'); t.className = 'offline'; t.textContent = 'offline charts'; h.insertBefore(t, h.querySelector('.grow')); } if (!on && t) t.remove(); }
/* datasets: [{label, data:[{x,y}], color, kind:'line'|'scatter'|'bar', dash, fill, yAxis:'y'|'y2', rot:[...]}]; opts: {xmin,xmax,zero,ref,timeFmt} */
function drawChart(panelId, canvasId, sets, opts = {}) {
  const cv = $('#' + canvasId); if (!cv) return; const off = !window.Chart; offlineTag(panelId, off);
  if (off) return fallbackDraw(cv, sets, opts);
  const tick = v => opts.timeFmt ? fmt.et(v, false) : fmt.fix(v, 0);
  const ds = sets.map(s => ({ label: s.label, data: s.data, type: s.kind === 'scatter' ? 'scatter' : s.kind === 'bar' ? 'bar' : 'line', borderColor: s.color, backgroundColor: s.bg || s.color,
    borderWidth: s.width || 1.2, pointRadius: s.kind === 'scatter' ? 5 : 0, pointStyle: s.style || 'circle', pointRotation: s.rot || 0, pointBackgroundColor: s.hollow ? 'transparent' : s.color,
    borderDash: s.dash || [], fill: s.fill || false, yAxisID: s.yAxis || 'y', spanGaps: false, tension: 0, order: s.kind === 'scatter' ? 0 : 1, parsing: false, hidden: !!s.hidden, maxBarThickness: 4 }));
  const scales = { x: { type: 'linear', min: opts.xmin, max: opts.xmax, grid: { display: false }, ticks: { color: cssVar('--muted'), font: { family: MONO, size: 10 }, callback: tick, maxTicksLimit: 8 } },
    y: { position: 'right', grid: { display: false }, ticks: { color: cssVar('--muted'), font: { family: MONO, size: 10 }, callback: v => fmt.fix(v, 0) } } };
  if (sets.some(s => s.yAxis === 'y2')) scales.y2 = { position: 'left', grid: { display: false }, ticks: { color: cssVar('--muted'), font: { family: MONO, size: 10 } } };
  const cfg = { type: 'line', data: { datasets: ds }, options: { animation: false, responsive: true, maintainAspectRatio: false, normalized: true, interaction: { mode: 'nearest', intersect: false },
    plugins: { legend: { display: false }, tooltip: { bodyFont: { family: MONO }, titleFont: { family: MONO }, callbacks: { title: it => it.length ? (opts.timeFmt ? fmt.et(it[0].parsed.x) + ' ET' : String(it[0].parsed.x)) : '',
      label: it => { const r = it.raw || {}; return `${it.dataset.label}: ${r.tip != null ? r.tip : fmt.fix(it.parsed.y, 2)}`; } } } }, scales } };
  let ch = charts[canvasId];
  if (ch) { ch.data.datasets = ds; ch.options.scales = scales; ch.update('none'); } else charts[canvasId] = new Chart(cv, cfg);
}
function fallbackDraw(cv, sets, opts) { // ~40 lines: polylines, dotted zero/reference line, min/max labels, triangles
  const W = cv.clientWidth || 600, H = cv.clientHeight || 200, dpr = window.devicePixelRatio || 1; cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H); g.font = '10px ' + MONO;
  const main = sets.filter(s => s.yAxis !== 'y2' && !s.hidden), pts = main.flatMap(s => s.data).filter(p => isNum(p.y));
  if (!pts.length) { g.fillStyle = cssVar('--muted'); g.fillText('no data', 8, 14); return; }
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y).concat(opts.zero ? [0] : [], isNum(opts.ref) ? [opts.ref] : []);
  const x0 = isNum(opts.xmin) ? opts.xmin : Math.min(...xs), x1 = isNum(opts.xmax) ? opts.xmax : Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const L = 4, Rm = 52, T = 8, B = 16, X = x => L + (x - x0) / ((x1 - x0) || 1) * (W - L - Rm), Y = y => T + (y1 - y) / ((y1 - y0) || 1) * (H - T - B);
  const dotted = (y, c) => { g.save(); g.setLineDash([3, 3]); g.strokeStyle = c; g.beginPath(); g.moveTo(L, Y(y)); g.lineTo(W - Rm, Y(y)); g.stroke(); g.restore(); };
  if (opts.zero) dotted(0, cssVar('--muted')); if (isNum(opts.ref)) dotted(opts.ref, cssVar('--amber'));
  for (const s of main) {
    g.strokeStyle = g.fillStyle = s.color; g.lineWidth = s.width || 1.2; g.setLineDash(s.dash || []);
    if (s.kind === 'scatter') { s.data.forEach((p, i) => { if (!isNum(p.y)) return; const x = X(p.x), y = Y(p.y), up = !(s.rot && s.rot[i]); g.beginPath(); g.moveTo(x, y + (up ? -5 : 5)); g.lineTo(x - 4, y + (up ? 3 : -3)); g.lineTo(x + 4, y + (up ? 3 : -3)); g.closePath(); s.hollow ? g.stroke() : g.fill(); }); continue; }
    g.beginPath(); let pen = false; for (const p of s.data) { if (!isNum(p.y)) { pen = false; continue; } pen ? g.lineTo(X(p.x), Y(p.y)) : g.moveTo(X(p.x), Y(p.y)); pen = true; } g.stroke();
  }
  g.setLineDash([]); g.fillStyle = cssVar('--muted'); g.textAlign = 'left'; g.fillText(fmt.fix(y1, 2), W - Rm + 3, T + 8); g.fillText(fmt.fix(y0, 2), W - Rm + 3, H - B);
  g.fillText(opts.timeFmt ? fmt.et(x0, false) : String(x0), L, H - 4); g.textAlign = 'right'; g.fillText(opts.timeFmt ? fmt.et(x1, false) : String(x1), W - Rm, H - 4);
}

/* ---- status bar + integrity ---- */
const STATE_PILL = { running: ['run', 'RUNNING'], stalled: ['warn', 'STALLED'], ended: ['off', 'ENDED'], off: ['off', 'OFF'], halted: ['down', 'HALTED'], loss_limit: ['down', 'LOSS LIMIT'] };
const intradayState = it => it.halted ? 'halted' : it.loss_limit_hit ? 'loss_limit' : (it.state || (it.running ? 'running' : 'off'));
const modeChip = m => m === 'live' ? 'LIVE' : 'DRY-RUN';
function renderStatus(d) {
  store.status = d; const it = d.intraday || {}, dl = d.daily || {}, lp = d.loop || {}, g = d.gates || {}, src = d.sources || {}, acc = store.account, p = [];
  p.push(d.gateway_connected ? pill('ok', `GATEWAY ${d.account_id || '?'} cid81`, 'ib_async readonly clientId 81') : pill('down', `GATEWAY DOWN · last seen ${acc && acc.as_of ? fmt.et(acc.as_of) + ' ET' : '—'}`, 'last successful IB tick'));
  const feed = String(d.feed || 'unknown'); p.push(pill(feed === 'ibkr' ? 'ok' : feed.startsWith('yahoo') ? 'warn' : 'off', 'FEED ' + feed.toUpperCase(), 'from feed_probe.ib_delay_minutes'));
  const st = intradayState(it), [sc, sl] = STATE_PILL[st] || STATE_PILL.off;
  p.push(pill(sc, `${sl} · ${it.strategy || '—'} ${isNum(it.equity_frac) ? it.equity_frac : '—'} ${modeChip(it.mode)} · last ${fmt.et(it.last_event_ts)} · P&L ${fmt.money(it.pnl_today, true)} · ${it.trades_today ?? '—'} tr · ${it.positions_n ?? '—'} pos`, 'intraday sleeve, from live/log/intraday-<date>.jsonl'));
  if (it.mode && it.mode !== 'live') p.push(pill('prov', 'DRY-RUN'));
  const kind = (dl.last_plan_kind || '—').toUpperCase().replace('_', '-');
  p.push(pill(dl.last_plan_kind === 'executed' ? 'ok' : 'off', `DAILY plan ${fmt.et(dl.last_plan_ts, false)} ET ${kind} · fills ${dl.last_fills_n ?? '—'} · next ${fmt.et(dl.next_run, false)}`, 'daily champion runner'));
  if (dl.last_plan_kind && dl.last_plan_kind !== 'executed') p.push(pill('prov', kind));
  const ls_ = String(lp.research_iterate_status || 'unknown'), lc = { ok: 'ok', success: 'ok', completed: 'ok', running: 'busy', error: 'down', failed: 'down', timeout: 'down' }[ls_] || 'off';
  p.push(pill(lc, `LOOP ${ls_} · last ${fmt.ageOf(lp.last_run_ts)} · next ${fmt.et(lp.next_run, false)}`, 'openclaw research-iterate'));
  p.push(g.approved_paper ? pill('ok', 'PAPER APPROVED', 'live/APPROVED_PAPER.md exists') : pill('down', 'NO APPROVAL', 'live/APPROVED_PAPER.md missing'));
  p.push(g.halt ? pill('down', 'HALT', 'live/HALT exists') : pill('off', 'halt: none', 'live/HALT absent'));
  p.push(g.halt_intraday ? pill('down', 'HALT INTRADAY', 'live/HALT_INTRADAY exists') : pill('off', 'halt_intraday: none', 'live/HALT_INTRADAY absent'));
  p.push('<span class="srcdots">' + ['ibkr', 'yahoo', 'alpaca', 'theta', 'fmp'].map(k => { const s = src[k] || {}; return `<span title="${esc(s.detail || '')}"><i class="${s.ok ? 'ok' : ''}"></i>${k.toUpperCase()}</span>`; }).join('') + '</span>');
  $('#pills').innerHTML = p.join(''); $('#p-status').classList.toggle('halt', !!(g.halt || g.halt_intraday));
  renderIntegrity(d.integrity || {});
}
function renderIntegrity(ig) {
  const rank = { red: 0, amber: 1, grey: 2 }, items = (ig.items || []).slice().sort((a, b) => (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3) || String(b.since || '').localeCompare(String(a.since || '')));
  let acked = 0; const rows = items.filter(i => { const a = store.acks[i.code + '|' + i.since]; if (a && i.severity !== 'red') { acked++; return false; } return true; }).map(i =>
    `<div class="it sev-${esc(i.severity)}"><i></i><b>${esc(i.code)}</b><span>${esc(i.message)}</span><span class="mut">since ${fmt.et(i.since)} ET</span><span class="mut">${esc(i.source || '')}</span>${i.severity !== 'red' ? `<span class="x" data-ack="${esc(i.code + '|' + i.since)}" title="ack (hide)">x</span>` : ''}</div>`);
  $('#integrity').innerHTML = rows.length ? rows.join('') : `<div class="banner green">0 integrity checks failing - ${ig.evaluated ?? '—'} evaluated at ${fmt.et(serverNowMs())} ET</div>`;
  $('#h-integrity').innerHTML = `${items.length} items · ${ig.evaluated ?? '—'} evaluated${acked ? ` · ${acked} acked` : ''}`;
  $('#int-asof').textContent = 'from /api/status';
}

/* ---- portfolio: KPI tiles + positions grouped by sleeve + open orders ---- */
function setTile(id, v, s, cls = '', warn) {
  const t = $('#' + id), tv = t.querySelector('.v'), html = `<span class="${cls}">${v}</span>`;
  if (tv.innerHTML !== html) { tv.innerHTML = html; t.classList.remove('flash'); void t.offsetWidth; t.classList.add('flash'); }
  t.querySelector('.s').innerHTML = s || ''; t.classList.toggle('warnb', !!warn);
}
function dayBaseline() { // first point of the current ET day, else intraday start.nav, else last non-mock plan net_liq
  const nb = store.nav && store.nav.day_baseline; if (nb && isNum(nb.nav)) return { nav: nb.nav, label: `vs ${fmt.et(nb.ts, false)} ${nb.source}` };
  const st = store.intraday && store.intraday.config && store.intraday.config.start; if (st && isNum(st.nav)) return { nav: st.nav, label: 'vs intraday start' };
  const lp = store.daily && (store.daily.last_executed_plan || (store.daily.last_plan && store.daily.last_plan.kind !== 'mock' ? store.daily.last_plan : null));
  return lp && isNum(lp.net_liq) ? { nav: lp.net_liq, label: 'vs last plan net_liq' } : null;
}
function renderPortfolio(d) {
  store.account = d; const gw = !!d.gateway_connected, nav = d.nav, bl = dayBaseline(), delta = bl && isNum(nav) ? nav - bl.nav : null;
  const b = $('#gw-banner'); b.hidden = gw; if (!gw) b.textContent = `GATEWAY DOWN - last known ${d.as_of ? fmt.et(d.as_of) + ' ET' : '—'}`;
  setTile('k-nav', fmt.money(nav), bl ? `Δday ${fmt.pnl(delta)} (${fmt.pct(isNum(delta) ? delta / bl.nav : null)}) ${bl.label}` : 'no day baseline', '', isNum(delta) && isNum(nav) && delta / nav < -0.01);
  setTile('k-cash', fmt.money(d.cash)); setTile('k-bp', fmt.money(d.buying_power));
  setTile('k-gross', fmt.money(d.gross_position_value), isNum(d.gross_position_value) && isNum(nav) ? fmt.fix(d.gross_position_value / nav, 2) + 'x NAV' : '');
  setTile('k-upnl', fmt.money(d.unrealized_pnl, true), '', fmt.sign(d.unrealized_pnl)); setTile('k-rpnl', fmt.money(d.realized_pnl, true), '', fmt.sign(d.realized_pnl));
  const it = (store.status || {}).intraday || {}, bk = store.intraday || {};
  setTile('k-ipnl', fmt.money(it.pnl_today, true), `${it.trades_today ?? '—'} tr · costs ${fmt.money(bk.costs ?? (bk.config && bk.config.book ? bk.config.book.costs : null))} · ${it.positions_n ?? '—'} pos`, fmt.sign(it.pnl_today));
  const pos = d.positions || [], dpos = pos.filter(x => x.sleeve === 'daily'), dp = dpos.length ? sum(dpos, x => x.unrealized_pnl) : null;
  const lp = store.daily && store.daily.last_executed_plan, gwt = lp && lp.targets ? sum(Object.values(lp.targets), Math.abs) : null;
  setTile('k-dpnl', fmt.money(dp, true), `${dpos.length} pos · gross w ${fmt.n2(gwt)}`, fmt.sign(dp));
  ['k-nav', 'k-cash', 'k-bp', 'k-gross', 'k-upnl', 'k-rpnl'].forEach(id => $('#' + id).classList.toggle('dim', !gw));
  const now = etParts(serverNowMs()), late = now.h * 60 + now.mi > 942, running = intradayState(it) === 'running', tgt = lp && lp.targets || {};
  const dailyBook = {}; ((store.daily || {}).fills || []).forEach(f => { if (isNum(f.qty)) dailyBook[f.symbol] = (dailyBook[f.symbol] || 0) + f.qty; });
  const groups = { intraday: [], daily: [], other: [] }; pos.forEach(x => (groups[x.sleeve] || groups.other).push(x));
  const rows = [], tot = { mv: 0, pnl: 0 }; let mism = 0;
  for (const [g, list] of Object.entries(groups)) {
    if (!list.length) continue; const gc = { intraday: 'pur', daily: 'blu', other: 'mut' }[g];
    let head = g.toUpperCase(); const book = bk.config && bk.config.book;
    if (g === 'intraday' && book && book.date === todayET() && book.mode === 'live') head += ` · book: ${Object.keys(book.pos || {}).length} pos · closed ${fmt.money(book.closed, true)} · costs ${fmt.money(book.costs)} · ${book.trades ?? '—'} tr`;
    rows.push(`<tr class="grp"><td colspan="11" class="${gc}">${esc(head)}</td></tr>`);
    const recon = x => { const bq = isNum(x.book_qty) ? x.book_qty : (g === 'daily' && isNum(dailyBook[x.symbol]) && dailyBook[x.symbol] !== x.shares ? dailyBook[x.symbol] : null);
      if (g === 'other') return ['down', 'FOREIGN', bq]; if (x.unpriced || !isNum(x.price)) return ['unpriced', 'UNPRICED', bq];
      if (bq != null && bq !== x.shares) return ['warn', 'MISMATCH', bq]; if (g === 'intraday' && !running && late) return ['warn', 'STRAGGLER', bq]; return ['ok', 'MATCH', bq]; };
    const items = list.map(x => ({ x, r: recon(x) })).sort((a, b) => (a.r[1] === 'MATCH') - (b.r[1] === 'MATCH') || Math.abs(b.x.market_value || 0) - Math.abs(a.x.market_value || 0));
    for (const { x, r } of items) {
      if (r[1] !== 'MATCH') mism++; const w = isNum(x.weight) ? x.weight : (isNum(x.market_value) && isNum(nav) ? x.market_value / nav : null), tw = g === 'daily' ? tgt[x.symbol] : null;
      rows.push(tr([`<span class="sym" data-sym="${esc(x.symbol)}">${esc(x.symbol)}</span>`, pill(g === 'intraday' ? 'intra' : g === 'daily' ? 'daily' : 'off', g.slice(0, 3)),
        R(`<span class="${x.shares < 0 ? 'neg' : ''}">${fmt.int(x.shares)}</span>`), R(r[2] != null ? `<span class="amb">book ${fmt.int(r[2])}</span>` : ''), R(fmt.px(x.avg_cost)),
        R(isNum(x.price) ? fmt.px(x.price) : fmt.none + ' ' + pill('unpriced', 'UNPRICED')), R(fmt.money(x.market_value)), R(fmt.pnl(x.unrealized_pnl)), R(fmt.pct(w, false)),
        R(g === 'daily' ? (isNum(tw) ? `${fmt.n2(tw)} <span class="mut">Δ${fmt.n2(isNum(w) ? w - tw : null)}</span>` : fmt.none) : ''), pill(r[0], r[1], 'book vs IB account')]));
    }
    const mv = sum(list, x => x.market_value), pn = sum(list, x => x.unrealized_pnl); tot.mv += mv; tot.pnl += pn;
    rows.push(tr(['', pill('off', 'subtotal'), '', '', '', '', R(fmt.money(mv)), R(fmt.pnl(pn)), R(isNum(nav) ? fmt.pct(mv / nav, false) : fmt.none), '', ''], 'sub'));
  }
  setBody('pos-table', rows, 'no positions'); $('#pos-foot').innerHTML = `positions ${pos.length} · MV ${fmt.money(tot.mv)} · uP&L ${fmt.pnl(tot.pnl)} · mismatches ${mism}` + (d.warnings || []).map(w => ` · <span class="amb">${esc(w)}</span>`).join('');
  const oo = d.open_orders || [], m0 = etToMs(todayET(), 0, 0), bad = oo.some(() => { const mm = now.h * 60 + now.mi; return !((mm >= 565 && mm <= 942) || (mm >= 944 && mm <= 955)); });
  $('#oo-note').hidden = !(oo.length && bad); $('#oo-note').textContent = `${oo.length} open order(s) outside the 09:25-15:42 / 15:44-15:55 ET windows`; void m0;
  setBody('oo-table', oo.map(o => tr([o.order_id, `<span class="sym" data-sym="${esc(o.symbol)}">${esc(o.symbol)}</span>`, pill(o.action === 'BUY' ? 'buy' : 'sell', o.action || '—'), R(fmt.int(o.qty)), esc(o.order_type), esc(o.status), R(fmt.int(o.filled)), esc(o.order_ref), R(o.client_id)])), 'no open orders');
  $('#h-portfolio').innerHTML = gw ? `IB ${fmt.ageOf(d.as_of)}` : `<span class="neg">GATEWAY DOWN - cached ${fmt.ageOf(d.as_of)}</span>`;
  const dl = $('#sym-dl'); dl.innerHTML = [...new Set(pos.map(x => x.symbol).concat((bk.trades || []).map(t => t.symbol), UNIVERSE, DAILY_UNI))].map(s => `<option value="${esc(s)}">`).join('');
}

/* ---- NAV history ---- */
function renderNav(d) {
  store.nav = d; const pts = (d.points || []).filter(p => isNum(parseTs(p.ts))).map(p => ({ ...p, x: parseTs(p.ts) }));
  const dash = pts.filter(p => p.source === 'dashboard' || !p.source), line = []; let prev = null;
  for (const p of dash) { if (prev && p.x - prev > 600000) line.push({ x: prev + 1, y: null }); line.push({ x: p.x, y: p.nav }); prev = p.x; }
  const mk = (src, style, rot) => ({ label: src, kind: 'scatter', style, rot, hollow: true, color: cssVar('--amber'), data: pts.filter(p => p.source === src).map(p => ({ x: p.x, y: p.nav, tip: fmt.money(p.nav) })) });
  const bl = d.day_baseline && isNum(d.day_baseline.nav) ? d.day_baseline.nav : null, sets = [{ label: 'nav', color: cssVar('--amber'), data: line, width: 1.5 }, mk('plan', 'circle', 0), mk('intraday_start', 'triangle', 0)];
  if (bl != null && pts.length) sets.push({ label: 'baseline', color: cssVar('--amber'), dash: [3, 3], width: 1, data: [{ x: pts[0].x, y: bl }, { x: pts[pts.length - 1].x, y: bl }] });
  if ($('#nav-gross').checked) sets.push({ label: 'gross', color: cssVar('--muted'), width: 1, data: dash.map(p => ({ x: p.x, y: isNum(p.gross) ? p.gross : null })) });
  if ($('#nav-cash').checked) sets.push({ label: 'cash', color: cssVar('--blue'), width: 1, data: dash.map(p => ({ x: p.x, y: isNum(p.cash) ? p.cash : null })) });
  $('#nav-empty').hidden = pts.length > 0; $('#nav-empty').textContent = 'no NAV history yet - the dashboard appends live/state/nav_history.jsonl once a minute while the gateway is up';
  drawChart('nav', 'nav-cv', sets, { timeFmt: true, ref: bl });
  const sn = d.sources_n || {}, last = pts[pts.length - 1], lastDash = dash[dash.length - 1], gw = store.status && store.status.gateway_connected;
  const stale = gw && lastDash && serverNowMs() - lastDash.x > 180000;
  $('#h-nav').innerHTML = last ? `newest ${fmt.etT(last.ts)} ET` + (stale ? ` <span class="amb">last sample written ${fmt.et(lastDash.ts)}</span>` : '') : '';
  $('#nav-legend').innerHTML = `dashboard ${sn.dashboard ?? dash.length} · plan ${sn.plan ?? '—'} · intraday_start ${sn.intraday_start ?? '—'} · mock excluded: ${d.mock_excluded ?? '—'} · days ${d.days ?? store.navDays}`;
}

/* ---- intraday sleeve ---- */
function renderIntraday(d) {
  store.intraday = d; const c = d.config || {}, st = c.start || {}, es = d.events_summary || {}, cnt = es.counts || {}, mode = d.mode || (st.dry_run ? 'dry_run' : 'live'), state = d.state || 'off';
  const [sc, sl] = STATE_PILL[d.halted ? 'halted' : d.loss_limit_hit ? 'loss_limit' : state] || STATE_PILL.off, lastAge = es.last_ts ? (serverNowMs() - parseTs(es.last_ts)) / 1000 : null;
  const p = etParts(serverNowMs()), m = p.h * 60 + p.mi, inSess = m >= 565 && m <= 942 && p.wd !== 'Sat' && p.wd !== 'Sun', lossFrac = isNum(d.pnl_today) && isNum(st.nav) ? d.pnl_today / st.nav : null;
  $('#h-intraday').innerHTML = [pill(sc, sl), pill(mode === 'live' ? 'ok' : 'prov', modeChip(mode)), chip(st.strategy || c.deployed && c.deployed.strategy || '—'), chip('frac ' + (isNum(st.equity_frac) ? st.equity_frac : '—')),
    chip('sleeve eq ' + fmt.money(c.sleeve_equity ?? (isNum(st.nav) && isNum(st.equity_frac) ? st.nav * st.equity_frac : null))), isNum(es.feed_delay_minutes) ? chip(`IB delayed ${Math.round(es.feed_delay_minutes)}m`) : '',
    `<span class="${lastAge > 180 && inSess ? 'neg' : 'mut'}">last event ${fmt.age(lastAge)}</span>`,
    `<span title="loss limit -2.5% of start NAV: ${fmt.pct(lossFrac)}">loss <span class="gauge"><i style="right:0;width:${isNum(lossFrac) ? Math.min(100, Math.max(0, -lossFrac / 0.025 * 100)) : 0}%"></i></span></span>`].join(' ');
  const drift = $('#in-drift'); drift.hidden = !c.drift; drift.textContent = 'CONFIG DRIFT - launch --params/--equity-frac/--strategy differ from live/intraday_config.json';
  const day = d.date || store.date, x0 = etToMs(day, 9, 30), x1 = etToMs(day, 16, 0), curve = (d.pnl_curve || []).map(q => ({ ...q, x: parseTs(q.t) })).filter(q => isNum(q.x));
  drawChart('intraday', 'pnl-cv', [{ label: 'pnl', color: cssVar('--green'), data: curve.map(q => ({ x: q.x, y: q.pnl })), fill: { target: 'origin', above: 'rgba(34,197,94,.15)', below: 'rgba(239,68,68,.15)' } },
    { label: 'zero', color: cssVar('--muted'), dash: [3, 3], width: 1, data: [{ x: x0, y: 0 }, { x: x1, y: 0 }] },
    { label: 'gross', color: cssVar('--muted'), width: 1, yAxis: 'y2', data: curve.map(q => ({ x: q.x, y: isNum(q.gross) ? q.gross : null })) }], { timeFmt: true, xmin: x0, xmax: x1, zero: true });
  const ld = d.last_decision || {}, book = c.book || {};
  $('#in-stats').innerHTML = [stat('P&L', fmt.pnl(d.pnl_today)), stat('trades', d.trades_today ?? '—'), stat('costs', fmt.money(book.costs ?? sum(d.trades || [], t => t.commission))), stat('gross', fmt.n2(curve.length ? curve[curve.length - 1].gross : null)),
    stat('positions', Object.keys(d.positions_now || {}).length + ` <span class="mut">(${esc(d.positions_source || 'none')})</span>`), stat('decisions', d.decisions_n ?? '—'), stat('last decision', ld.t ? fmt.et(ld.t, false) + ' ET' : '—')].join('');
  const dep = c.deployed || {}, pr = dep.params || {}, al = pr.alloc || {};
  $('#in-config').innerHTML = [chip(`orb ${al.orb ?? '—'}`), chip(`vwap ${al.vwap_trend ?? '—'}`), chip(`late_momo ${al.late_momo ?? '—'}`), chip(`per_sym ${pr.per_symbol ?? '—'}`), chip(`gross ${pr.gross ?? '—'}`), chip(`equity_frac ${dep.equity_frac ?? '—'}`)].join('');
  const tg = ld.targets || {}; $('#in-targets').innerHTML = Object.keys(tg).length ? Object.entries(tg).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([s, w]) => wbar(s, w)).join('') : '<div class="empty">no decision yet</div>';
  $('#in-events').innerHTML = Object.entries(cnt).map(([k, v]) => chip(`${k} ${v}`, k === 'notify_failed' ? 'dim' : RED_EVENTS.has(k) ? 'hl' : '')).join('') + (es.bad_lines ? chip(`bad lines ${es.bad_lines}`, 'dim') : '');
  const trades = (d.trades || []).slice().sort((a, b) => parseTs(b.ts) - parseTs(a.ts));
  setBody('in-trades', trades.map(t => tr([fmt.etT(t.ts), `<span class="sym" data-sym="${esc(t.symbol)}">${esc(t.symbol)}</span>`, pill(t.qty < 0 ? 'sell' : 'buy', t.qty < 0 ? 'SELL' : 'BUY'), R(fmt.int(Math.abs(t.qty))), R(fmt.px(t.avg_price)), R(fmt.n2(t.commission)),
    esc(t.status) + (t.partial ? ' ' + pill('warn', 'PARTIAL') : ''), R(t.id ?? ''), R(fmt.n2(t.latency_s))])), 'no fills in the log');
  $('#in-tfoot').innerHTML = `fills ${trades.length} · commissions ${fmt.money(sum(trades, t => t.commission))} · notional ${fmt.money(sum(trades, t => Math.abs((t.qty || 0) * (t.avg_price || 0))))} · dead ${(d.dead_orders || []).length} · pending ${(d.pending_orders || []).length}`;
  $('#in-pos').innerHTML = Object.entries(d.positions_now || {}).map(([s, q]) => chip(`${s} ${fmt.int(q)}`, q < 0 ? 'neg' : '', `data-sym="${esc(s)}"`)).join('') || '<span class="mut">flat</span>';
  const errs = (d.errors || []).slice(-8); $('#in-errors').innerHTML = errs.length ? errs.map(e => `<div class="${RED_EVENTS.has(e.event) ? 'neg' : 'mut'}">${fmt.et(e.ts)} <span class="ev">${esc(e.event)}</span>${e.count > 1 ? ` x${e.count}` : ''} ${fmt.trunc(e.detail, 200)}</div>`).join('') : '<span class="mut">none</span>';
  const ex = es.excluded || {}; $('#in-note').textContent = (ex.replay_decisions || ex.foreign_date_snapshots) ? `excluded: replay decisions ${ex.replay_decisions || 0}, foreign-date snapshots ${ex.foreign_date_snapshots || 0}` : '';
  const dl = $('#dates-dl'); if (es.available_dates && es.available_dates.length) dl.innerHTML = es.available_dates.map(x => `<option value="${esc(x)}">`).join('');
}

/* ---- daily sleeve ---- */
function planCard(pl, title, cur) {
  if (!pl) return ''; const kind = (pl.kind || '—').toUpperCase().replace('_', '-'), dg = pl.diagnostics || {}, stt = dg.state || {}, tg = pl.targets || {}, tw = sum(Object.values(tg), Math.abs);
  const chips = [['regime', dg.regime_reason], ['vol', isNum(dg.regime_vol) ? `${fmt.n2(dg.regime_vol)}/${fmt.n2(dg.regime_median)}` : null], ['vol_scale', dg.vol_scale], ['gross_w', dg.gross_weight], ['margin', dg.margin_used], ['eff_exp', dg.effective_exposure],
    ['held', stt.held ? stt.held.map(h => `${h}${stt.held_age && stt.held_age[h] != null ? ':' + stt.held_age[h] : ''}`).join(' ') : null], ['winners', dg.winners ? dg.winners.join(' ') : null]].filter(c => c[1] != null);
  return `<div class="card${pl.kind === 'mock' ? ' mockp' : ''}"><h3>${esc(title)} ${pill(pl.kind === 'executed' ? 'ok' : 'prov', kind)} <span class="mono">${fmt.etD(pl.ts)} ET</span></h3>
    <div class="row mono small">${stat('signal', esc(pl.signal))}${stat('as_of', esc(pl.as_of))}${stat('net_liq', fmt.money(pl.net_liq))}${stat('gross w', fmt.n2(tw))}</div>
    ${Object.entries(tg).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([s, w]) => wbar(s, w, cur ? cur[s] : null)).join('')}
    ${(pl.orders || []).length ? `<div class="mono small">${pl.orders.map(o => `<div class="orow"><span class="sym" data-sym="${esc(o.symbol)}">${esc(o.symbol)}</span> ${o.delta > 0 ? '+' : ''}${fmt.int(o.delta)} @ ${fmt.px(o.price)} <span class="mut">≈ ${fmt.money(isNum(o.delta) && isNum(o.price) ? Math.abs(o.delta * o.price) : null)}</span></div>`).join('')}</div>` : '<div class="mut small">no orders</div>'}
    <div>${chips.map(([k, v]) => chip(`${k} ${typeof v === 'number' ? fmt.fix(v, v % 1 ? 3 : 0) : v}`)).join('')}</div></div>`;
}
function renderDaily(d) {
  store.daily = d; const ch = d.champion || {}, cs = ch.stats || {}, lp = d.last_plan, ex = d.last_executed_plan, acc = store.account || {}, cur = {};
  (acc.positions || []).forEach(x => { cur[x.symbol] = isNum(x.weight) ? x.weight : (isNum(x.market_value) && isNum(acc.nav) ? x.market_value / acc.nav : null); });
  $('#dl-champ').innerHTML = ch.algorithm ? `${esc(ch.algorithm)} · CAR ${esc(cs['Compounding Annual Return'])} · Sharpe ${esc(cs['Sharpe Ratio'])} · DD ${esc(cs.Drawdown)} · <span data-commit="${esc(ch.commit)}">${esc(ch.commit)}</span> · promoted ${esc(String(ch.promoted_at || '').slice(5, 10))}` : '<span class="mut">no champion</span>';
  $('#dl-plan').innerHTML = planCard(lp, 'Last plan', cur) || '<div class="empty">no plan for this date</div>';
  $('#dl-exec').innerHTML = lp && ex && lp.kind !== 'executed' && ex.ts !== lp.ts ? planCard(ex, 'Last executed plan', cur) : '';
  const orders = (ex || lp || {}).orders || [], ref = {}; orders.forEach(o => { ref[o.symbol] = o.price; });
  setBody('dl-fills', (d.fills || []).map(f => { const rp = isNum(f.ref_price) ? f.ref_price : ref[f.symbol], slip = isNum(rp) && isNum(f.avg_price) && isNum(f.qty) ? Math.sign(f.qty) * (f.avg_price - rp) / rp * 1e4 : null;
    return tr([fmt.etT(f.ts), `<span class="sym" data-sym="${esc(f.symbol)}">${esc(f.symbol)}</span>`, R(isNum(f.qty) ? fmt.int(f.qty) : `<span class="mut">${fmt.int(f.filled)} ?</span>`), R(fmt.px(f.avg_price)), esc(f.status), R(isNum(slip) ? `<span class="${slip > 0 ? 'neg' : 'pos'}">${fmt.fix(slip, 1)}</span>` : fmt.none)]); }), 'no fills');
  const w = d.warnings || []; $('#dl-warn').innerHTML = w.map(x => `<div class="${x.event === 'connect_failed' || x.event === 'notify_failed' ? 'amb' : 'neg'}">${x.count} ${esc(x.event)} · last ${fmt.et(x.last_ts, false)} ET ${fmt.trunc(x.detail, 120)}</div>`).join('');
  setBody('dl-hist', (d.history || []).map(h => { const tg = h.targets || {}, mx = Math.max(1, ...Object.values(tg).map(Math.abs));
    return tr([esc(h.date), pill(h.kind === 'executed' ? 'ok' : 'prov', (h.kind || '—').toUpperCase().replace('_', '-')), Object.entries(tg).map(([s, v]) => `<span class="sym" data-sym="${esc(s)}">${esc(s)}</span> ${fmt.fix(v * 100, 0)}<span class="gauge" style="width:${Math.round(Math.abs(v) / mx * 30)}px"><i style="left:0;right:0;background:var(--blue)"></i></span>`).join(' / ') || fmt.none,
      R(h.fills_n ?? ''), R(fmt.money(h.net_liq)), [h.connect_failed_n && `cf ${h.connect_failed_n}`, h.refused_n && `ref ${h.refused_n}`, h.flatten_n && `flat ${h.flatten_n}`].filter(Boolean).join(' ') || '']); }), 'no sessions');
  const p = etParts(serverNowMs()), wk = p.wd !== 'Sat' && p.wd !== 'Sun', late = p.h * 60 + p.mi > 947, today = d.date === todayET();
  const bad = w.filter(x => x.event === 'refused' || x.event === 'flatten'), banner = $('#dl-banner');
  banner.hidden = !(today && ((wk && late && !ex) || bad.length)); banner.textContent = bad.length ? `${bad.map(x => x.event + ' x' + x.count).join(', ')} today` : 'weekday past 15:47 ET and no executed plan today';
  const stt = d.state || {}; $('#dl-next').innerHTML = `next run ${fmt.et(d.next_run || ((store.status || {}).daily || {}).next_run, false)} ET · last_run.json dry_run: ${esc(String(stt.dry_run ?? '—'))} · signal ${esc(stt.signal || '—')}`;
  $('#h-daily').innerHTML = lp ? `plan ${fmt.et(lp.ts, false)} ET ${pill(lp.kind === 'executed' ? 'ok' : 'prov', (lp.kind || '—').toUpperCase().replace('_', '-'))}` : '';
}

/* ---- price chart: closes line + VWAP + volume bars + trade markers (Chart.js) ---- */
function chartUrl() { const s = ($('#c-sym').value || store.sym || 'NVDA').trim().toUpperCase(); if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(s)) return null; store.sym = s; ls.set('sym', s);
  return `/api/chart?symbol=${encodeURIComponent(s)}&date=${store.date}&source=${$('#c-src').value}`; }
function chartInterval() { const it = (store.status || {}).intraday || {}, held = store.intraday && store.intraday.positions_now && store.intraday.positions_now[store.sym] != null;
  return store.date !== todayET() ? 0 : (intradayState(it) === 'running' && held ? 10000 : 60000); }
function renderChart(d, p) {
  const bars = (d.bars || []).map(b => ({ ...b, x: parseTs(b.t) })).filter(b => isNum(b.x)), empty = $('#c-empty');
  if (d.pending && !bars.length) { store.chartRetries++; empty.hidden = false; empty.textContent = store.chartRetries > 10 ? 'no bars' : `pending - bars are being fetched (${store.chartRetries})`;
    if (store.chartRetries <= 10) p.nextOverride = (d.retry_in || 3) * 1000; $('#h-chart').innerHTML = pill('busy', 'pending'); return; }
  store.chartRetries = 0; empty.hidden = bars.length > 0; empty.textContent = bars.length ? '' : (d.error || 'no bars');
  const x0 = etToMs(d.date || store.date, 9, 30), x1 = etToMs(d.date || store.date, 16, 0), sets = [{ label: 'close', color: cssVar('--amber'), width: 1.3, data: bars.map(b => ({ x: b.x, y: b.c, tip: `o ${fmt.px(b.o)} h ${fmt.px(b.h)} l ${fmt.px(b.l)} c ${fmt.px(b.c)} v ${fmt.int(b.v)}` })) }];
  if ($('#c-vwap').checked) { let pv = 0, vv = 0; sets.push({ label: 'vwap', color: cssVar('--cyan'), width: 1, data: bars.map(b => { const tp = (b.h + b.l + b.c) / 3; pv += tp * (b.v || 0); vv += b.v || 0; return { x: b.x, y: vv ? pv / vv : null }; }) }); }
  if ($('#c-vol').checked) sets.push({ label: 'volume', kind: 'bar', color: 'rgba(125,136,150,.35)', yAxis: 'y2', data: bars.map(b => ({ x: b.x, y: b.v })) });
  const trades = (d.trades || []).map(t => ({ ...t, x: parseTs(t.t) })).filter(t => isNum(t.x));
  if ($('#c-markers').checked && trades.length) for (const [slv, col] of [['intraday', cssVar('--purple')], ['daily', cssVar('--blue')]]) {
    const ts = trades.filter(t => (t.sleeve || 'intraday') === slv); if (!ts.length) continue;
    sets.push({ label: slv, kind: 'scatter', style: 'triangle', color: col, rot: ts.map(t => t.qty < 0 ? 180 : 0), data: ts.map(t => ({ x: t.x, y: t.price, tip: `${t.qty > 0 ? 'BUY' : 'SELL'} ${fmt.int(Math.abs(t.qty))}@${fmt.px(t.price)}${t.commission != null ? ' comm ' + fmt.n2(t.commission) : ''}${t.id != null ? ' id ' + t.id : ''}` })) });
  }
  drawChart('chart', 'price-cv', sets, { timeFmt: true, xmin: x0, xmax: x1 });
  const last = bars[bars.length - 1], srcp = { yahoo: 'YAHOO 1m', ibkr_parquet: 'IBKR STORE', alpaca_parquet: 'ALPACA STORE' }[d.source_used] || (d.source_used || 'source ?');
  $('#h-chart').innerHTML = `${esc(d.symbol || store.sym)} ${esc(d.date || store.date)} · ${bars.length} bars ${pill('info', srcp)} · ${trades.length} markers` + (last ? ` · last bar ${fmt.et(last.x, false)} ET · ${fmt.age((serverNowMs() - last.x) / 1000)} behind clock` : '');
}
function chartSymbol(sym, date) { if (sym) { $('#c-sym').value = sym.toUpperCase(); } if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) setDate(date); store.chartRetries = 0; panels.chart.refresh(); $('#p-chart').scrollIntoView({ block: 'nearest' }); }
function setDate(date) { if (date === store.date) return; store.date = date; $('#gdate').value = date; store.chartRetries = 0; ['intraday', 'daily', 'chart'].forEach(k => panels[k].refresh()); }

/* ---- strategies ---- */
function renderStrategies(d) {
  const ch = d.champion_daily || {}, cs = ch.stats || {}, cr = ch.criteria || {}, fw = d.framework || {}, held = new Set(((store.account || {}).positions || []).map(x => x.symbol));
  if (fw.UNIVERSE) store.uni = new Set(fw.UNIVERSE); if (fw.DAILY_SLEEVE_UNIVERSE) store.duni = new Set(fw.DAILY_SLEEVE_UNIVERSE);
  const dd = num(cs.Drawdown), lim = num(cr.max_drawdown_limit), dds = (d.daily_docstrings || {})[ch.algorithm];
  $('#st-daily').innerHTML = `<h3>Daily champion</h3><div><b>${esc(ch.algorithm || '—')}</b> <span class="mono mut">${esc(ch.class || '')}</span> · <span class="mut">${esc(dds || '')}</span></div>
    <div>${[...store.duni].map(s => symChip(s, held.has(s))).join('')}</div>
    <div class="row mono small">${stat('promoted', fmt.etD(ch.promoted_at) + ' ET')}${stat('commit', `<span data-commit="${esc(ch.commit)}">${esc(ch.commit || '—')}</span>`)}${['Compounding Annual Return', 'Sharpe Ratio', 'Drawdown', 'Total Orders', 'Total Fees', 'Probabilistic Sharpe Ratio'].map(k => stat(k.replace('Compounding Annual Return', 'CAR').replace('Probabilistic Sharpe Ratio', 'PSR'), esc(cs[k] ?? '—'))).join('')}</div>
    <div class="tw short"><table><thead><tr><th scope="col">Stat</th><th scope="col">Champion</th><th scope="col">Rule</th></tr></thead><tbody>
      ${tr(['CAR', esc(cs['Compounding Annual Return']), 'must_beat: ' + esc((cr.must_beat || []).join(', '))])}${tr(['Sharpe', esc(cs['Sharpe Ratio']), 'tolerance ' + esc(cr.sharpe_tolerance)])}
      ${tr(['Drawdown', esc(cs.Drawdown), `tolerance ${esc(cr.drawdown_tolerance_points)} pt · limit ${esc(cr.max_drawdown_limit)} <span class="gauge" style="width:100px"><i style="left:0;width:${isNum(dd) && isNum(lim) ? Math.min(100, dd / lim * 100) : 0}%;background:var(--amber)"></i></span> ${isNum(dd) ? fmt.fix(dd, 1) : '—'}/${isNum(lim) ? lim : '—'}`])}
      ${tr(['min trades', '', esc(cr.min_trades)])}</tbody></table></div>
    <div class="small mut">${esc(cr.note || '')}</div>${ch.note ? `<details><summary>read the promotion note</summary><pre>${esc(ch.note)}</pre></details>` : ''}
    <div class="small mono mut">research/champion.json -> scripts/paper_trade.py -> task Quant Paper Rebalance 15:45 ET</div>`;
  const di = d.deployed_intraday || {}, pr = di.params || {}, al = pr.alloc || {}, mods = d.intraday_modules || [], names = new Set(mods.map(m => m.name));
  const bar = (k, v) => `<div class="wb${v ? '' : ' hollow'}"><span class="k">${esc(k)}</span><div class="track"><i class="fill" style="left:0;width:${Math.min(100, (v || 0) * 100)}%;background:var(--purple)"></i></div><span class="val">${isNum(v) ? fmt.fix(v, 2) : '—'}${v ? '' : ' <span class="mut">retired</span>'}</span></div>`;
  $('#st-intra').innerHTML = `<h3>Intraday sleeve (deployed)</h3><div class="row mono small">${stat('strategy', esc(di.strategy || '—'))}${stat('equity_frac', isNum(di.equity_frac) ? fmt.fix(di.equity_frac * 100, 0) + '% of NAV' : '—')}${stat('per_symbol', esc(pr.per_symbol ?? '—'))}${stat('gross', esc(pr.gross ?? '—'))}</div>
    ${['orb', 'vwap_trend', 'late_momo'].map(k => bar(k, al[k])).join('')}
    <div class="small mono mut">sub_params ${esc(JSON.stringify(pr.sub_params || {}))}</div>
    ${di.strategy && !names.has(di.strategy) ? `<div class="banner amber">drift: deployed strategy "${esc(di.strategy)}" is not among the intraday modules</div>` : ''}
    <div class="row">${['MIN_CHANGE', 'PER_SYMBOL_HARD_CAP', 'GROSS_HARD_CAP', 'DAILY_LOSS_LIMIT', 'FLATTEN_MINUTE', 'EXIT_MINUTE', 'SLIPPAGE_BPS'].map(k => { const v = fw[k]; const t = /MINUTE/.test(k) && isNum(v) ? `${v} (${pad(Math.floor((570 + v) / 60))}:${pad((570 + v) % 60)} ET)` : (v ?? '—'); return chip(`${k} ${t}`); }).join('')}</div>
    <div>${[...store.uni].map(s => symChip(s, held.has(s))).join('')}</div>
    ${di._comment || di._a10_note ? `<details><summary>why this config</summary><pre>${esc([di._comment, di._a10_note].filter(Boolean).join('\n\n'))}</pre></details>` : ''}
    <div class="h3">Modules</div>${mods.map(m => `<div class="small"><b class="mono">${esc(m.name)}</b>${di.strategy === m.name ? ' ' + pill('ok', 'deployed') : ''} - ${esc(m.docstring_first_line || '')}${Object.keys(m.params || {}).length ? `<details><summary>params</summary><pre>${esc(JSON.stringify(m.params, null, 1))}</pre></details>` : ''}</div>`).join('')}
    <div class="h3">Daily algorithms</div>${(d.daily_algorithms || []).map(n => `<div class="small"><b class="mono">${esc(n)}</b>${n === ch.algorithm ? ' <span class="crown" title="champion">&#9819;</span>' : ''} - ${esc((d.daily_docstrings || {})[n] || '')}</div>`).join('')}`;
}

/* ---- research summary ---- */
function renderResearch(d) {
  store.summary = d; const ch = d.champion || {}, cs = ch.stats || {}, cnt = d.counts || {}, bm = d.backlog_meta || {};
  $('#rs-counts').innerHTML = `experiments ${d.experiments_n ?? '—'} · daily ${cnt.daily ?? '—'} · intraday ${cnt.intraday ?? '—'} · bad lines ${cnt.bad_lines ?? '—'} · ledger ${d.ledger_mtime ? fmt.etD(d.ledger_mtime) + ' ET' : '—'}`;
  $('#rs-champ').innerHTML = `<h3>Champion</h3><div><b class="mono">${esc(ch.algorithm || '—')}</b> <span data-commit="${esc(ch.commit)}" class="mono">${esc(ch.commit || '')}</span> · promoted ${fmt.etD(ch.promoted_at)} ET</div>
    <div class="row mono small">${Object.entries(cs).map(([k, v]) => stat(k, esc(v))).join('')}</div><div class="small mut">${fmt.trunc(ch.tag, 200)}</div>`;
  setBody('rs-last', (d.last_20 || []).map(r => { const s = r.stats || {}; return tr([fmt.etD(r.ts), `<span data-search="${esc(r.algorithm)}" class="sym">${esc(r.algorithm)}</span>${s.track === 'intraday' || r.track === 'intraday' ? ' ' + pill('intra', 'intra') : ''}`, fmt.trunc(r.tag, 60),
    R(`<span class="${fmt.sign(num(s['Compounding Annual Return']))}">${esc(s['Compounding Annual Return'] ?? '—')}</span>`), R(esc(s['Sharpe Ratio'] ?? '—')), R(esc(s.Drawdown ?? '—')), R(esc(s['Avg Daily PnL'] ?? ''))]); }), 'no runs');
  setBody('rs-alg', (d.by_algorithm || []).map(a => tr([`<span data-search="${esc(a.algorithm)}" class="sym">${esc(a.algorithm)}</span>`, R(a.runs), R(fmt.n2(num(a.best_sharpe))), R(isNum(num(a.best_car)) ? fmt.fix(num(a.best_car), 2) + '%' : fmt.none), fmt.etD(a.last_ts)])), 'none');
  $('#rs-backlog-h').textContent = `Backlog open ${bm.open_n ?? (d.backlog_open || []).length} · done ${bm.done_n ?? '—'}`;
  $('#rs-backlog').innerHTML = (bm.objective_excerpt ? `<div class="excerpt mut">${esc(bm.objective_excerpt)}</div>` : '') + (d.backlog_open || []).map(b => `<details class="${b.done ? 'done' : ''}"><summary><span class="chip lit" data-search="${esc(b.id)}">${esc(b.id)}</span> ${esc(b.title)}${b.done ? ' ' + pill('off', 'done-in-open') : ''}</summary><div class="excerpt">${esc(b.text)}</div></details>`).join('');
  $('#rs-journal').innerHTML = (d.journal_latest || []).map(j => `<details><summary>${esc(j.title)}</summary><div class="excerpt">${esc(j.text_excerpt)}</div></details>`).join('') || '<span class="mut">none</span>';
  const bh = d.blockers_headings || []; $('#rs-blockers').innerHTML = bh.length ? bh.map(h => `<div class="card" style="border-color:var(--amber)">${esc(h)}</div>`).join('') + `<details><summary>excerpt</summary><div class="excerpt">${esc(d.blockers_excerpt)}</div></details>` : '<span class="pos">none open</span>' + (d.blockers_excerpt ? `<details><summary>excerpt</summary><div class="excerpt">${esc(d.blockers_excerpt)}</div></details>` : '');
  const git = ((panels.system || {}).lastGood || {}).git_log || [], inGit = git.length ? (git.some(g => ch.commit && g.hash && g.hash.startsWith(ch.commit)) ? 'yes' : 'no') : '—';
  $('#rs-notes').textContent = `champion run_dir exists: ${d.champion_run_dir_exists == null ? '—' : d.champion_run_dir_exists ? 'yes' : 'no'} · champion commit in last 30 git commits: ${inGit} · reports ${(d.reports || []).length}`;
  $('#h-research').innerHTML = `${d.experiments_n ?? '—'} exp`;
  const sel = $('#lg-alg'), cur = sel.value; sel.innerHTML = '<option value="">all algorithms</option>' + (d.by_algorithm || []).map(a => `<option value="${esc(a.algorithm)}">${esc(a.algorithm)} (${a.runs})</option>`).join(''); sel.value = cur;
  const key = `${d.experiments_n}|${(d.last_20 || [])[0] ? d.last_20[0].ts : ''}`; if (store.ledger && key !== store.ledgerKey && !$('#p-ledger').classList.contains('collapsed')) panels.ledger.refresh(); store.ledgerKey = key;
}

/* ---- ledger explorer: fetched on expand, filtered/sorted client-side ---- */
const LCOLS = { daily: [['ts', 'ts'], ['algorithm', 'algorithm'], ['tag', 'tag'], ['CAR', 'car'], ['Sharpe', 'sharpe'], ['Sortino', 'sortino'], ['DD', 'dd'], ['PSR', 'psr'], ['Orders', 'orders'], ['Fees', 'fees'], ['commit', 'commit']],
  intraday: [['ts', 'ts'], ['algorithm', 'algorithm'], ['tag', 'tag'], ['start-end', 'start'], ['sessions', 'sessions'], ['$/day', 'avg_daily_pnl'], ['costs/day', 'costs_per_day'], ['trades/day', 'trades_per_day'], ['Sharpe', 'sharpe'], ['CAR', 'car'], ['DD', 'dd'], ['worst day', 'worst_day'], ['LL days', 'loss_limit_days'], ['commit', 'commit']] };
const STATKEY = { car: 'Compounding Annual Return', sharpe: 'Sharpe Ratio', sortino: 'Sortino Ratio', dd: 'Drawdown', psr: 'Probabilistic Sharpe Ratio', orders: 'Total Orders', fees: 'Total Fees', avg_daily_pnl: 'Avg Daily PnL', costs_per_day: 'Costs Per Day', trades_per_day: 'Trades Per Day', worst_day: 'Worst Day', loss_limit_days: 'Loss Limit Days', sessions: 'Sessions' };
const lval = (r, k) => k === 'ts' ? parseTs(r.ts) : STATKEY[k] ? ((r.parsed || {})[k] ?? num((r.stats || {})[STATKEY[k]])) : String(r[k] ?? '');
function renderLedger(d) {
  if (d.rows) store.ledger = d.rows; const rows = store.ledger || [], q = $('#lg-q').value.trim().toLowerCase(), alg = $('#lg-alg').value, from = $('#lg-from').value, to = $('#lg-to').value, tk = store.ledgerTrack;
  const smoke = new Set(['_template', 'd1_data_smoke', 'd2_minute_smoke']), champ = ((store.summary || {}).champion || {}), cdd = num((champ.stats || {}).Drawdown);
  const list = rows.filter(r => (tk === 'all' || r.track === tk) && (!alg || r.algorithm === alg) && (!$('#lg-smoke').checked || !smoke.has(r.algorithm)) && (!$('#lg-prom').checked || !/not promotable/i.test(r.tag || ''))
    && (!store.ledgerCommit || String(r.commit || '').startsWith(store.ledgerCommit)) && (!q || `${r.tag} ${r.commit} ${r.class} ${r.algorithm}`.toLowerCase().includes(q))
    && (!from || etDateStr(parseTs(r.ts)) >= from) && (!to || etDateStr(parseTs(r.ts)) <= to));
  const { key, dir } = store.ledgerSort; list.sort((a, b) => { const x = lval(a, key), y = lval(b, key); if (x == null || x === '' || Number.isNaN(x)) return 1; if (y == null || y === '' || Number.isNaN(y)) return -1; return (x < y ? -1 : x > y ? 1 : 0) * dir; });
  const cols = LCOLS[tk === 'all' ? 'daily' : tk]; $('#lg-table thead').innerHTML = '<tr>' + cols.map(([h, k]) => `<th scope="col" class="sortable${key === k ? ' sorted' : ''}${STATKEY[k] ? ' r' : ''}" data-sort="${k}">${esc(h)}${key === k ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>';
  const cell = (r, k) => { const s = r.stats || {}, v = s[STATKEY[k]]; if (k === 'ts') return fmt.etD(r.ts); if (k === 'algorithm') return esc(r.algorithm) + (r.track === 'intraday' ? ' ' + pill('intra', 'i') : ''); if (k === 'tag') return `<span class="wrap">${fmt.trunc(r.tag, 90)}</span>`;
    if (k === 'commit') return `<span data-commit="${esc(r.commit)}" class="mono">${esc(r.commit || '')}</span>`; if (k === 'start') return esc(`${r.start || ''}..${r.end || ''}`);
    const n = lval(r, k), cls = k === 'car' || k === 'avg_daily_pnl' ? fmt.sign(n) : k === 'dd' && isNum(n) && isNum(cdd) && n > cdd ? 'amb' : ''; return R(`<span class="${cls}">${esc(v ?? (isNum(n) ? n : '—'))}</span>`); };
  const shown = list.slice(0, 500);
  setBody('lg-table', shown.map((r, i) => tr(cols.map(([, k]) => cell(r, k)), r.commit && champ.commit && r.commit === champ.commit ? 'hl' : '', `data-row="${i}"`)), rows.length ? 'no rows match' : 'no ledger rows loaded');
  $('#lg-foot').innerHTML = `rows ${shown.length}${list.length > 500 ? ' of ' + list.length + ' matching' : ''} / total ${d.total ?? rows.length}${store.ledgerCommit ? ` · commit filter <span class="chip lit" data-commit="">${esc(store.ledgerCommit)} x</span>` : ''} · ` + ((store.summary || {}).by_algorithm || []).map(a => chip(`${a.algorithm} ${a.runs}`, '', `data-alg="${esc(a.algorithm)}"`)).join('');
  $('#lg-table tbody')._rows = shown;
}
function ledgerDetail(row) { // inline detail row under the clicked ledger row: stats, params (diff vs deployed), run_dir, champion delta
  const dep = (((panels.strategies || {}).lastGood || {}).deployed_intraday || {}).params, ch = ((store.summary || {}).champion || {}), cp = ch.parsed || {}, pr = row.parsed || {};
  const delta = ['car', 'sharpe', 'dd'].map(k => `${k} ${isNum(pr[k]) && isNum(cp[k]) ? (pr[k] - cp[k] > 0 ? '+' : '') + fmt.fix(pr[k] - cp[k], 3) : '—'}`).join(' · ');
  const pj = row.params ? JSON.stringify(row.params, null, 1) : '', diff = dep && row.params && String(row.algorithm).startsWith('intraday/') ? JSON.stringify(row.params) === JSON.stringify(dep) ? 'params == deployed' : 'params differ from deployed: ' + JSON.stringify(dep) : '';
  return `<tr class="sub"><td colspan="20" class="wrap"><div class="row mono small">${Object.entries(row.stats || {}).map(([k, v]) => stat(k, esc(v))).join('')}</div>
    <div class="mono small">run_dir ${esc(row.run_dir || '—')} · commit <span data-commit="${esc(row.commit)}">${esc(row.commit || '—')}</span> · ${esc(row.start || '')}..${esc(row.end || '')}${row.slippage_bps != null ? ' · slippage_bps ' + esc(row.slippage_bps) : ''}</div>
    <div class="mono small amb">vs champion: ${delta}</div>${pj ? `<details><summary>params</summary><pre>${esc(pj)}</pre><div class="small mut">${esc(diff)}</div></details>` : ''}<div class="small">${esc(row.tag)}</div></td></tr>`;
}

/* ---- data network + options ---- */
function renderData(d) {
  const st = d.stores || {}, ev = d.events || {}, th = d.theta || {}, kp = d.keys_present || {}, rows = [];
  for (const [name, store_] of [['ibkr_minute', st.ibkr_minute], ['alpaca_minute', st.alpaca_minute]]) {
    const syms = (store_ || {}).symbols || [], ok = syms.filter(s => isNum(s.sessions)), failed = syms.length - ok.length, lasts = syms.map(s => s.last).filter(Boolean).sort(), firsts = syms.map(s => s.first).filter(Boolean).sort();
    const lastMs = lasts.length ? parseTs(lasts[lasts.length - 1]) : NaN, age = isNum(lastMs) ? (serverNowMs() - lastMs) / 86400000 : null;
    rows.push(tr([esc(name), R(syms.length), R((ok.length ? `${Math.min(...ok.map(s => s.sessions))}..${Math.max(...ok.map(s => s.sessions))}` : '') + (failed ? ` <span class="neg">scan failed ${failed}</span>` : '')), esc(`${firsts[0] || '—'}..${lasts[lasts.length - 1] || '—'}`), `<span class="${age > 4 ? 'amb' : ''}">${isNum(age) ? fmt.fix(age, 1) + ' d' : '—'}</span>`]));
    if (syms.length) rows.push(`<tr class="sub"><td colspan="5"><details><summary>per symbol</summary>${syms.map(s => chip(`${s.symbol} ${isNum(s.sessions) ? s.sessions : 'scan failed'} ${s.first || ''}..${s.last || ''}`, isNum(s.sessions) ? '' : 'hl', `data-sym="${esc(s.symbol)}"`)).join('')}</details></td></tr>`);
  }
  setBody('da-stores', rows, 'no stores');
  $('#da-misc').innerHTML = `LEAN daily ${st.lean_daily_n ?? '—'} zips · LEAN minute ${(st.lean_minute_symbols || []).map(s => esc(s)).join(' ') || '—'}<br>earnings.json generated ${esc(ev.generated || '—')} · symbols ${ev.symbols_n ?? '—'}<br>THETA ${pill(th.alive ? 'ok' : 'down', th.alive ? 'ALIVE' : 'DOWN', 'http://127.0.0.1:25503')} ${esc(th.plan || '')}` + (d.scan_as_of ? ` · scan ${fmt.et(d.scan_as_of)} ET` : '');
  $('#da-keys').innerHTML = Object.entries(kp).map(([k, v]) => pill(v ? 'ok' : 'off', `${v ? '✓' : '✗'} ${k}`, 'presence only - values are never served')).join(' ') || '<span class="mut">—</span>';
}
function renderOptions(d) {
  $('#op-title').textContent = `${d.symbol || ''} ${d.nearest_expiration ? 'exp ' + d.nearest_expiration : ''} ${isNum(d.spot) ? 'spot ' + fmt.px(d.spot) : ''}`;
  const q = d.atm_quotes || []; if (!q.length) { $('#op-body').innerHTML = `<div class="empty">${esc(d.message || (d.alive ? 'no quotes' : 'Theta terminal down - no quotes'))}</div>`; return; }
  const byStrike = {}; q.forEach(x => { (byStrike[x.strike] = byStrike[x.strike] || {})[String(x.right || '').toUpperCase()[0]] = x; });
  const c = k => k ? `${fmt.n2(k.bid)}/${fmt.n2(k.ask)} <span class="mut">${fmt.n2(k.mid)}</span>` : fmt.none;
  $('#op-body').innerHTML = `<div class="tw short"><table><thead><tr><th scope="col" class="r">Strike</th><th scope="col" class="r">Call bid/ask mid</th><th scope="col" class="r">Put bid/ask mid</th></tr></thead><tbody>${Object.keys(byStrike).sort((a, b) => a - b).slice(0, 5).map(k => tr([R(fmt.px(+k)), R(c(byStrike[k].C)), R(c(byStrike[k].P))])).join('')}</tbody></table></div>`;
}

/* ---- system ---- */
const RESULT_TEXT = { 0: 'OK', 267009: 'RUNNING', 267011: 'NEVER RUN', 267014: 'TERMINATED' };
function renderSystem(d) {
  const sec = d.sections || {}, stampOf = (k, id) => { const s = sec[k] || {}; $('#' + id).innerHTML = (s.as_of ? `<span class="mut">${fmt.et(s.as_of)} ET</span>` : '') + (s.error ? ` <span class="neg" title="${esc(s.error)}">${esc(String(s.error).slice(0, 80))}</span>` : ''); };
  stampOf('openclaw', 'sy-auto-asof'); stampOf('runs', 'sy-runs-asof'); stampOf('tasks', 'sy-tasks-asof'); stampOf('git', 'sy-git-asof'); stampOf('gateway_log', 'sy-gw-asof');
  const first = ['research-iterate', 'research-review'], au = (d.automations || []).slice().sort((a, b) => (first.indexOf(b.name) + 1) - (first.indexOf(a.name) + 1));
  setBody('sy-auto', au.map(a => tr([esc(a.name) || `<span class="mut">${esc(a.raw_row)}</span>`, esc(a.schedule), esc(a.next), esc(a.last), pill(/ok|success|idle|scheduled/i.test(a.status || '') ? 'ok' : /run/i.test(a.status || '') ? 'busy' : /err|fail|time/i.test(a.status || '') ? 'down' : 'off', a.status || '—')])), 'openclaw list unavailable');
  const runs = []; for (const [job, list] of Object.entries(d.last_runs || {})) (list || []).slice(0, 5).forEach(r => runs.push({ job, ...r }));
  setBody('sy-runs', runs.map(r => tr([esc(r.job), pill(/ok|success|complete/i.test(r.status || '') ? 'ok' : /run/i.test(r.status || '') ? 'busy' : 'down', r.status || '—'), R(fmt.dur(r.durationMs)), r.ts ? fmt.etD(r.ts) : fmt.none, fmt.trunc(r.error, 60), `<details><summary>${fmt.trunc(r.summary_tail, 160)}</summary><pre>${esc(String(r.summary_tail || '').slice(-300))}</pre></details>`])), 'no runs');
  setBody('sy-tasks', (d.scheduled_tasks || []).map(t => { const rt = t.last_result_text || RESULT_TEXT[t.last_result] || (t.last_result == null ? '—' : '0x' + Number(t.last_result).toString(16) + ' unknown');
    return tr([esc(t.name), pill(/run/i.test(t.state || '') ? 'busy' : /ready/i.test(t.state || '') ? 'ok' : 'off', t.state || '—'), t.next_run ? fmt.etD(t.next_run) : fmt.none, t.last_run ? fmt.etD(t.last_run) : fmt.none, `<span class="${/OK|RUNNING/.test(rt) ? '' : 'amb'}">${esc(rt)}</span>`]); }), 'no tasks');
  const champ = (((store.summary || {}).champion) || {}).commit; $('#sy-git').innerHTML = (d.git_log || []).map(g => `<div class="ln${champ && g.hash && g.hash.startsWith(champ) ? ' amb' : ''}"><span data-commit="${esc(g.hash)}" title="click: copy hash + filter the ledger">${esc(g.hash)}</span>${champ && g.hash && g.hash.startsWith(champ) ? ' <span class="crown">&#9819;</span>' : ''} ${esc(g.subject)}</div>`).join('') || '<div class="empty">no git log</div>';
  store.gwTail = d.gateway_log_tail || []; renderGwTail();
  if (store.summary && !$('#rs-notes').textContent.includes('yes')) renderResearch(store.summary);
}
function renderGwTail() {
  const only = $('#gw-filter').classList.contains('on'), lines = store.gwTail.slice(-20).filter(l => !only || /ERROR|WARN/i.test(l.level || ''));
  $('#sy-gw').innerHTML = lines.map(l => l.raw != null ? `<div class="ln mut">${esc(String(l.raw).slice(0, 200))}</div>` : `<div class="ln${/stalled session/i.test(l.message || '') ? ' amb' : ''}"><span class="mut">${fmt.et(l.time)}</span> <span class="lv-${esc(String(l.level || '').toUpperCase())}">${esc(l.level || '')}</span> <span class="mut">${esc(l.subsystem || '')}</span> ${esc(String(l.message || '').slice(0, 200))}</div>`).join('') || '<div class="empty">no lines</div>';
}

/* ---- raw log viewer (sub-panel of SYSTEM) ---- */
const evClass = e => e === 'fill' ? 'ev-fill' : e === 'order' ? 'ev-order' : e === 'decision' ? 'ev-dim' : e === 'snapshot' ? 'ev-snapshot' : e === 'alert' ? 'ev-alert' : e === 'notify_failed' ? 'ev-dim' : (RED_EVENTS.has(e) || /_error$|_failed$/.test(e)) ? 'ev-red' : '';
function logsUrl() { if (!store.logsOpened) return null; return `/api/logs?name=${$('#lv-name').value}&date=${$('#lv-date').value || todayET()}&n=${$('#lv-n').value}`; }
function renderLogs(d) {
  store.logLines = d.lines || []; const evs = {}; store.logLines.forEach(l => { evs[l.event] = (evs[l.event] || 0) + 1; });
  $('#lv-chips').innerHTML = Object.entries(evs).sort((a, b) => b[1] - a[1]).map(([e, n]) => `<span class="chip${store.logEv === e ? ' lit' : ''}" data-ev="${esc(e)}">${esc(e)} ${n}</span>`).join('');
  if ($('#lv-name').value === 'alerts') { const und = store.logLines.filter(l => l.delivered === false), errs = [...new Set(und.map(l => l.error).filter(Boolean))];
    $('#lv-summary').innerHTML = `<span class="${und.length ? 'amb' : ''}">${store.logLines.length} alerts, ${store.logLines.length - und.length} delivered${errs.length ? ' · ' + esc(errs.join(' | ')) : ''}</span>`; } else $('#lv-summary').textContent = '';
  drawLogLines(); $('#lv-foot').textContent = `${d.file || '—'} · ${isNum(d.size) ? fmt.fix(d.size / 1024, 1) + ' KB' : '—'} · mtime ${d.mtime ? fmt.etD(d.mtime) + ' ET' : '—'} · lines skipped as invalid JSON: ${d.skipped ?? 0}`;
}
function drawLogLines() {
  const q = $('#lv-q').value.trim().toLowerCase(), lines = (store.logLines || []).filter(l => (!store.logEv || l.event === store.logEv) && (!q || JSON.stringify(l).toLowerCase().includes(q)));
  $('#lv-lines').innerHTML = lines.map(l => { const rest = Object.entries(l).filter(([k]) => k !== 'ts' && k !== 'event').map(([k, v]) => `${k}=${typeof v === 'object' && v !== null ? `<details style="display:inline"><summary style="display:inline">{…}</summary>${esc(JSON.stringify(v))}</details>` : esc(v)}`).join(' ');
    return `<div class="ln"><span class="mut" title="${esc(l.ts)}">${fmt.et(l.ts)}</span><span class="ev ${evClass(l.event)}">${esc(l.event)}</span>${rest}</div>`; }).join('') || '<div class="empty">no lines</div>';
}
function openLogs(name, date) { store.logsOpened = true; if (name) $('#lv-name').value = name; if (date) $('#lv-date').value = date; const sys = $('#p-system'); sys.classList.remove('collapsed'); panels.logs.refresh(); $('#s-logs').scrollIntoView({ block: 'nearest' }); }

/* ---- commands, keyboard, cross-references ---- */
function runCommand(s) {
  s = s.trim(); if (!s) return; let m;
  if ((m = /^([A-Za-z][A-Za-z0-9.\-]{0,9})(?:\s+(\d{4}-\d{2}-\d{2}))?$/.exec(s)) && !/^(exp|log)$/i.test(m[1])) return chartSymbol(m[1], m[2]);
  if ((m = /^exp\s+(\S+)/i.exec(s))) { expandLedger(); $('#lg-alg').value = m[1]; if ($('#lg-alg').value !== m[1]) { $('#lg-alg').value = ''; $('#lg-q').value = m[1]; } return renderLedger({}); }
  if ((m = /^log\s+(intraday|daily|alerts)(?:\s+(\d{4}-\d{2}-\d{2}))?/i.exec(s))) return openLogs(m[1].toLowerCase(), m[2]);
  expandLedger(); $('#lg-q').value = s; renderLedger({});
}
function expandLedger() { const p = $('#p-ledger'); if (p.classList.contains('collapsed')) toggleCollapse(p); if (!store.ledger) panels.ledger.refresh(); p.scrollIntoView({ block: 'nearest' }); }
function toggleCollapse(p) { const c = p.classList.toggle('collapsed'); p.querySelector('.chev').innerHTML = c ? '&#9656;' : '&#9662;'; ls.set('collapsed', Object.fromEntries($$('.collapsible').map(x => [x.id, x.classList.contains('collapsed')]))); if (!c && p.id === 'p-ledger' && !store.ledger) panels.ledger.refresh(); }
function filterByCommit(hash) { store.ledgerCommit = hash || ''; if (hash) { try { navigator.clipboard.writeText(hash); } catch (e) { /* clipboard unavailable */ } } expandLedger(); renderLedger({}); $$('#sy-git .ln').forEach(l => l.classList.toggle('hl', !!hash && l.textContent.startsWith(hash))); }
document.addEventListener('click', e => {
  const t = e.target.closest('[data-sym],[data-commit],[data-search],[data-retry],[data-ack],[data-sort],[data-days],[data-track],[data-alg],[data-ev],[data-row],.chev'); if (!t) return;
  if (t.matches('.chev')) return toggleCollapse(t.closest('.panel'));
  if (t.dataset.sym != null) return chartSymbol(t.dataset.sym);
  if (t.dataset.commit != null) return filterByCommit(t.dataset.commit);
  if (t.dataset.search != null) { expandLedger(); $('#lg-q').value = t.dataset.search; return renderLedger({}); }
  if (t.dataset.retry) return panels[t.dataset.retry].refresh();
  if (t.dataset.ack) { store.acks[t.dataset.ack] = 1; ls.set('acks', store.acks); return renderIntegrity((store.status || {}).integrity || {}); }
  if (t.dataset.sort) { const k = t.dataset.sort; store.ledgerSort = { key: k, dir: store.ledgerSort.key === k ? -store.ledgerSort.dir : -1 }; return renderLedger({}); }
  if (t.dataset.days) { store.navDays = +t.dataset.days; $$('#nav-range button').forEach(b => b.classList.toggle('on', b === t)); return panels.nav.refresh(); }
  if (t.dataset.track) { store.ledgerTrack = t.dataset.track; $$('#lg-track button').forEach(b => b.classList.toggle('on', b === t)); return renderLedger({}); }
  if (t.dataset.alg != null) { $('#lg-alg').value = t.dataset.alg; return renderLedger({}); }
  if (t.dataset.ev != null) { store.logEv = store.logEv === t.dataset.ev ? '' : t.dataset.ev; return drawLogLines(); }
  if (t.dataset.row != null) { const rows = $('#lg-table tbody')._rows || [], nx = t.nextElementSibling; if (nx && nx.classList.contains('sub')) nx.remove(); else t.insertAdjacentHTML('afterend', ledgerDetail(rows[+t.dataset.row])); }
});
document.addEventListener('keydown', e => {
  const inInput = /INPUT|SELECT|TEXTAREA/.test(e.target.tagName), help = $('#help');
  if (e.key === 'Escape') { help.hidden = true; if (inInput) e.target.blur(); return; }
  if (inInput) { if (e.key === 'Enter' && e.target.id === 'cmd') { runCommand(e.target.value); e.target.value = ''; e.target.blur(); } return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const panelKeys = { 1: 'portfolio', 2: 'nav', 3: 'intraday', 4: 'daily', 5: 'chart', 6: 'strategies', 7: 'research', 8: 'ledger', 9: 'data', 0: 'system' };
  if (e.key === '/') { e.preventDefault(); $('#cmd').focus(); } else if (e.key === 'r') refreshAll(); else if (e.key === '?') help.hidden = !help.hidden; else if (e.key === 'l') openLogs();
  else if (e.key === 'p') { store.paused = !store.paused; store.pausedAt = Date.now(); if (!store.paused) refreshAll(); }
  else if (e.key === 'd') { const ds = ((store.intraday || {}).events_summary || {}).available_dates || [], prev = ds.filter(x => x < todayET()).sort().pop(); setDate(store.date === todayET() && prev ? prev : todayET()); }
  else if (panelKeys[e.key]) { const p = $('#p-' + panelKeys[e.key]); if (p.classList.contains('collapsed')) toggleCollapse(p); p.scrollIntoView({ block: 'start' }); p.focus(); }
});

/* ---- init ---- */
function init() {
  $('#gdate').value = store.date; $('#lv-date').value = store.date; $('#c-sym').value = store.sym;
  const collapsed = ls.get('collapsed', { 'p-ledger': true }); $$('.collapsible').forEach(p => { const c = collapsed[p.id] ?? p.classList.contains('collapsed'); p.classList.toggle('collapsed', !!c); p.querySelector('.chev').innerHTML = c ? '&#9656;' : '&#9662;'; });
  const dailyIv = () => { const p = etParts(serverNowMs()), m = p.h * 60 + p.mi; return m >= 940 && m <= 955 ? 10000 : 60000; };
  const defs = [['status', '#p-status', '/api/status', 10000, renderStatus], ['portfolio', '#p-portfolio', '/api/account', 10000, renderPortfolio],
    ['nav', '#p-nav', () => `/api/nav_history?days=${store.navDays}`, 60000, renderNav], ['intraday', '#p-intraday', () => `/api/sleeves/intraday?date=${store.date}`, () => store.date === todayET() ? 10000 : 60000, renderIntraday],
    ['daily', '#p-daily', () => `/api/sleeves/daily?date=${store.date}`, dailyIv, renderDaily], ['chart', '#p-chart', chartUrl, chartInterval, renderChart],
    ['strategies', '#p-strategies', '/api/strategies', 60000, renderStrategies], ['research', '#p-research', '/api/research/summary', 60000, renderResearch],
    ['ledger', '#p-ledger', () => $('#p-ledger').classList.contains('collapsed') && store.ledger ? null : '/api/research/experiments?limit=2000', 0, renderLedger],
    ['data', '#p-data', '/api/data', 60000, renderData], ['options', '#s-options', () => `/api/options?symbol=${encodeURIComponent(store.sym || 'SPY')}`, 60000, renderOptions],
    ['system', '#p-system', '/api/system', 60000, renderSystem], ['logs', '#s-logs', logsUrl, () => ($('#lv-date').value || todayET()) === todayET() ? 10000 : 0, renderLogs]];
  defs.forEach(([id, sel, ep, iv, fn], i) => { const p = new Panel(id, sel, ep, iv, fn); if (id === 'ledger') p.el.classList.remove('skel'); if (id !== 'ledger' && id !== 'logs') setTimeout(() => p.tick(true), i * 250); });
  panels.ledger.base = () => 0; panels.ledger.schedule = () => {}; // on demand only
  panels.logs.interval = function () { const b = this.base(); return b ? (document.hidden ? b * 6 : b) : 3600000; };
  if (!collapsed['p-ledger']) panels.ledger.refresh();
  $('#gdate').addEventListener('change', e => setDate(e.target.value || todayET()));
  $('#c-sym').addEventListener('change', () => chartSymbol($('#c-sym').value)); $('#c-src').addEventListener('change', () => panels.chart.refresh());
  ['c-markers', 'c-vwap', 'c-vol'].forEach(id => $('#' + id).addEventListener('change', () => panels.chart.lastGood && renderChart(panels.chart.lastGood, panels.chart)));
  ['nav-gross', 'nav-cash'].forEach(id => $('#' + id).addEventListener('change', () => panels.nav.lastGood && renderNav(panels.nav.lastGood)));
  ['lg-alg', 'lg-q', 'lg-from', 'lg-to', 'lg-smoke', 'lg-prom'].forEach(id => $('#' + id).addEventListener('input', () => renderLedger({})));
  $('#lv-fetch').addEventListener('click', () => openLogs()); $('#lv-q').addEventListener('input', drawLogLines); ['lv-name', 'lv-date', 'lv-n'].forEach(id => $('#' + id).addEventListener('change', () => store.logsOpened && panels.logs.refresh()));
  $('#gw-filter').addEventListener('click', e => { e.target.classList.toggle('on'); renderGwTail(); }); $('#help-btn').addEventListener('click', () => { $('#help').hidden = false; }); $('#help').addEventListener('click', () => { $('#help').hidden = true; });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshAll(); });
  setInterval(tickStamps, 1000); tickStamps();
  if (window.__chartFailed || !window.Chart) ['nav', 'intraday', 'chart'].forEach(id => offlineTag(id, true));
}
try { init(); } catch (e) { console.error('init failed', e); }
