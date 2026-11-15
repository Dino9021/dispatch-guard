// Browser tab labels: every tab a session drives starts with "[<port>-<n> <role>] ", unused tabs "閒置".
// Owner 2026-11-14: 「請你在 tab 頁籤上面標注號碼與使用人的名字」「未來不管誰開 Play Wright 都要這樣處理」.
// ADR Memory/tasks/20261115-090000-browser-tab-labels. Ported from Game docs/browser-tab-label.cjs and
// browser-tab-keeper.cjs, talking to Chrome's DevTools port directly - no Playwright, no npm install.
//
//   node browser_tabs.cjs label <port> <role> [url-part]   tag my tabs (once; re-run after a full navigation)
//   node browser_tabs.cjs keep  <port>                     re-apply lost tags every second, until the browser goes
//
// Never closes the browser or a tab. label never takes a tab tagged for another role.
'use strict';

if (typeof WebSocket !== 'function' || typeof fetch !== 'function') {
  console.error('browser_tabs: this Node has no built-in WebSocket/fetch (Node 22 or later has both).');
  process.exit(2);
}

const TAG = /^\[\d+-\d+ [^\]]*\] /;
const IDLE = '閒置';
// ⛔ Must stay Game's code (same globals, same regex): two observers that differ undo each other for ever
// and froze a page in the round-1 review (ADR B2).
const OBSERVER = (tag) => `(() => {
  const strip = (t) => t.replace(/^\\[\\d+-\\d+ [^\\]]*\\] /, '');
  window.__tabTagText = ${JSON.stringify(tag)};
  const fix = () => { const want = window.__tabTagText + strip(document.title); if (document.title !== want) document.title = want; };
  fix();
  if (!window.__tabTag) {
    window.__tabTag = new MutationObserver(fix);
    window.__tabTag.observe(document.querySelector('title') || document.head, { childList: true, subtree: true, characterData: true });
  }
  return document.title;
})()`;

const base = (port) => `http://127.0.0.1:${port}`;
const withTimeout = (p, ms, what) => Promise.race([p, new Promise((_, no) => setTimeout(() => no(new Error(what + ' timed out')), ms))]);

async function pages(port) {
  const list = await withTimeout(fetch(base(port) + '/json/list').then((r) => r.json()), 3000, '/json/list');
  // /json/list is newest first; number oldest first so a new tab does not renumber the others.
  return list.filter((t) => t.type === 'page' && /^https?:/.test(t.url)).reverse();
}

async function evaluate(target, expression) {
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  try {
    await withTimeout(new Promise((ok, no) => { ws.onopen = ok; ws.onerror = () => no(new Error('ws error')); }), 3000, 'connect');
    const reply = new Promise((ok) => { ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id === 1) ok(m); }; });
    ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate', params: { expression, returnByValue: true } }));
    const m = await withTimeout(reply, 3000, 'evaluate'); // a tab showing alert() never answers
    return m.result && m.result.result ? m.result.result.value : undefined;
  } finally {
    ws.close();
  }
}

async function label(port, role, match) {
  const list = await pages(port);
  for (let i = 0; i < list.length; i++) {
    const t = list[i];
    const m = t.title.match(TAG);
    const owner = m ? m[0].slice(1, -2).split(' ').slice(1).join(' ') : '';
    if (owner && owner !== IDLE && owner !== role) {          // another role's tab: never taken
      if (match && t.url.includes(match)) console.log('skip (tagged for ' + owner + '): ' + t.url);
      continue;
    }
    const mine = match ? t.url.includes(match) : true;
    const who = mine ? role : (owner ? null : IDLE);          // an untagged tab I don't use becomes idle
    if (!who) continue;
    const tag = `[${port}-${i + 1} ${who}] `;
    try { await evaluate(t, OBSERVER(tag)); console.log(tag + t.url); }
    catch (e) { console.log('skip (' + e.message + '): ' + t.url); }
  }
}

async function keep(port) {
  const me = process.pid + '-' + Date.now();
  const browser = async () => (await withTimeout(fetch(base(port) + '/json/version').then((r) => r.json()), 3000, '/json/version')).webSocketDebuggerUrl;
  const first = await browser();
  const last = new Map(); // target id -> tag
  for (;;) {
    let now;
    try { now = await browser(); } catch { console.log('browser gone, exiting'); return; }
    if (now !== first) { console.log('a different browser answers on this port, exiting'); return; }
    let list = [];
    try { list = await pages(port); } catch { /* next pass */ }
    for (let i = 0; i < list.length; i++) {
      const t = list[i];
      try {
        // One keeper per browser: another keeper's beat younger than 3 s means this one leaves.
        const beat = await evaluate(t, `(() => { const b = window.__tabKeeperBeat; const mine = ${JSON.stringify(me)};
          if (b && b.id !== mine && Date.now() - b.t < 3000) return 'other';
          window.__tabKeeperBeat = { id: mine, t: Date.now() }; return document.title; })()`);
        if (beat === 'other') { console.log('another keeper is running on this browser, exiting'); return; }
        const m = String(beat || '').match(TAG);
        if (m) { last.set(t.id, m[0]); continue; }
        const tag = last.get(t.id) || `[${port}-${i + 1} ${IDLE}] `;
        last.set(t.id, tag);
        await evaluate(t, OBSERVER(tag));
        console.log(new Date().toTimeString().slice(0, 8), 'restored', tag + t.url.slice(0, 80));
      } catch { /* loading, closed, or a dialog open: next pass */ }
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

const [cmd, port, role, match] = process.argv.slice(2);
if (cmd === 'label' && port && role) label(port, role, match).then(() => process.exit(0), (e) => { console.error(e.message); process.exit(1); });
else if (cmd === 'keep' && port) keep(port).then(() => process.exit(0), (e) => { console.error(e.message); process.exit(1); });
else { console.error('usage: node browser_tabs.cjs label <port> <role> [url-part] | keep <port>'); process.exit(2); }
