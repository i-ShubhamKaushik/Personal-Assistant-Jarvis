const WS_URL = 'ws://localhost:6789';
const OUTER_CIRC = 2 * Math.PI * 100;
const INNER_CIRC = 2 * Math.PI * 76;

let outerTarget = 0, innerTarget = 0;
let outerCur = 0, innerCur = 0;
let barsData = Array(28).fill(0.05);
let currentState = 'offline';
let cmdCount = 0;
let startTime = Date.now();
let ws = null;
let reconnectTimer = null;

const STATE_CFG = {
  offline:   {outer:0.00, inner:0.00, text:'OFFLINE',    sub:'CONNECTING...'},
  standby:   {outer:0.08, inner:0.00, text:'STANDBY',    sub:'SAY · JARVIS'},
  wake:      {outer:0.40, inner:0.20, text:'WAKE WORD',  sub:'DETECTED'},
  active:    {outer:0.88, inner:0.65, text:'ACTIVE',     sub:'AWAITING COMMAND'},
  thinking:  {outer:1.00, inner:0.92, text:'THINKING',   sub:'PROCESSING...'},
  mute:      {outer:0.02, inner:0.00, text:'MUTED',      sub:'OFFLINE'},
};

const CHIP_MAP = {standby:'chipStandby', wake:'chipWake', active:'chipActive', thinking:'chipThinking'};

function applyState(s) {
  currentState = s;
  const cfg = STATE_CFG[s] || STATE_CFG.offline;
  outerTarget = cfg.outer;
  innerTarget = cfg.inner;
  document.getElementById('stateText').textContent = cfg.text;
  document.getElementById('stateSub').textContent  = cfg.sub;
  document.getElementById('statVal').textContent   = cfg.text;
  Object.entries(CHIP_MAP).forEach(([k,id]) => {
    document.getElementById(id).className = 'chip' + (k === s ? ' lit' : '');
  });
}

function log(kind, text) {
  const box = document.getElementById('logBox');
  const ts  = new Date().toLocaleTimeString('en-GB',{hour12:false});
  const div = document.createElement('div');
  div.className = 'log-entry';
  div.innerHTML = `<span class="ts">${ts}</span><span class="t-${kind}">${escHtml(text)}</span>`;
  box.appendChild(div);
  if (box.children.length > 200) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
  if (kind === 'cmd') cmdCount++;
  document.getElementById('cmdCount').textContent = cmdCount;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function lerp(a,b,t){ return a + (b-a)*t; }

function animate() {
  outerCur = lerp(outerCur, outerTarget, 0.055);
  innerCur = lerp(innerCur, innerTarget, 0.055);
  document.getElementById('ringOuter').style.strokeDashoffset = OUTER_CIRC*(1-outerCur);
  document.getElementById('ringInner').style.strokeDashoffset = INNER_CIRC*(1-innerCur);

  const active = currentState === 'active' || currentState === 'thinking';
  const waking = currentState === 'wake';
  const count = 28;
  for (let i = 0; i < count; i++) {
    if (active)      barsData[i] = lerp(barsData[i], 0.15 + Math.random()*0.72, 0.32);
    else if (waking) barsData[i] = lerp(barsData[i], 0.05 + Math.random()*0.28, 0.20);
    else             barsData[i] = lerp(barsData[i], 0.02 + Math.sin(Date.now()/900+i)*0.04, 0.10);
  }

  let html = '';
  for (let i = 0; i < count; i++) {
    const a  = (i/count)*2*Math.PI - Math.PI/2;
    const r1 = 60, r2 = 60 + barsData[i]*20;
    const x1 = 110 + r1*Math.cos(a), y1 = 110 + r1*Math.sin(a);
    const x2 = 110 + r2*Math.cos(a), y2 = 110 + r2*Math.sin(a);
    const op = (currentState==='mute'||currentState==='offline') ? 0.04 : 0.22 + barsData[i]*0.58;
    html += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="#00A8FF" stroke-width="1.8" stroke-opacity="${op.toFixed(2)}" stroke-linecap="round"/>`;
  }
  document.getElementById('bars').innerHTML = html;
  requestAnimationFrame(animate);
}

/* ── WebSocket ── */
function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    clearTimeout(reconnectTimer);
    document.getElementById('connDot').className   = 'conn-dot on';
    document.getElementById('connLabel').textContent = 'CONNECTED';
    log('sys', '[ UI connected to Jarvis backend ]');
    applyState('standby');
  };

  ws.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === 'state') applyState(msg.state);
    if (msg.type === 'log')   log(msg.kind, msg.text);
  };

  ws.onclose = () => {
    document.getElementById('connDot').className   = 'conn-dot';
    document.getElementById('connLabel').textContent = 'RECONNECTING';
    applyState('offline');
    log('err', '[ Connection lost — retrying in 3s... ]');
    reconnectTimer = setTimeout(connect, 3000);
  };

  ws.onerror = () => ws.close();
}

/* ── Manual input (type commands from the UI) ── */
document.getElementById('sendBtn').onclick = () => {
  const inp = document.getElementById('cmdInput');
  const val = inp.value.trim();
  if (!val || !ws || ws.readyState !== WebSocket.OPEN) return;
  log('cmd', '[Manual]: ' + val);
  inp.value = '';
};
document.getElementById('cmdInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('sendBtn').click();
});

/* ── Uptime ── */
setInterval(() => {
  const s = Math.floor((Date.now()-startTime)/1000);
  const m = Math.floor(s/60), sc = s%60;
  document.getElementById('uptimeVal').textContent =
    String(m).padStart(2,'0') + ':' + String(sc).padStart(2,'0');
}, 1000);

animate();
connect();