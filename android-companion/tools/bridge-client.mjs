#!/usr/bin/env node
// Test client for the Earshot bridge. Pretends to be the glasses app.
// Needs Node 22+ (built-in WebSocket). No npm install needed.
//
//   node tools/bridge-client.mjs ping
//   node tools/bridge-client.mjs speak repeat        (type_it | repeat | thanks)
//   node tools/bridge-client.mjs say "Any text"
//   node tools/bridge-client.mjs type-screen         (waits and prints typed text; Ctrl+C to quit)
//   node tools/bridge-client.mjs hide-type-screen
//   node tools/bridge-client.mjs status
//   node tools/bridge-client.mjs alert doorbell right medium
//                                                    (rings the phone like the glasses do: resent every
//                                                     5 s; Ctrl+C ends it. label dir tier all optional)
//   node tools/bridge-client.mjs listen
//   node tools/bridge-client.mjs raw '{"v":1,"type":"ping"}'
//   node tools/bridge-client.mjs                     (interactive: type commands)
//
// Options: --url ws://HOST:PORT[/path]   (default ws://127.0.0.1:8765)
//          --no-adb                       (don't run "adb forward" for you)
// With the default URL it runs "adb forward tcp:8765 tcp:8765" so the
// laptop's 127.0.0.1:8765 reaches the phone's server over USB.

import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import readline from 'node:readline';

const args = process.argv.slice(2);
let url = 'ws://127.0.0.1:8765';
let useAdb = true;
const rest = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--url') url = args[++i];
  else if (args[i] === '--no-adb') useAdb = false;
  else rest.push(args[i]);
}
const [cmd, ...cmdArgs] = rest;

function findAdb() {
  const candidates = [];
  for (const v of ['ANDROID_HOME', 'ANDROID_SDK_ROOT']) if (process.env[v]) candidates.push(join(process.env[v], 'platform-tools'));
  if (process.env.LOCALAPPDATA) candidates.push(join(process.env.LOCALAPPDATA, 'Android', 'Sdk', 'platform-tools'));
  if (process.env.HOME) candidates.push(join(process.env.HOME, 'Library', 'Android', 'sdk', 'platform-tools'), join(process.env.HOME, 'Android', 'Sdk', 'platform-tools'));
  for (const dir of candidates) {
    for (const name of ['adb.exe', 'adb']) if (existsSync(join(dir, name))) return join(dir, name);
  }
  return 'adb';
}

const u = new URL(url);
if (useAdb && ['127.0.0.1', 'localhost'].includes(u.hostname)) {
  const port = u.port || '80';
  try {
    execFileSync(findAdb(), ['forward', `tcp:${port}`, `tcp:${port}`], { stdio: 'pipe' });
    log('SYS', `adb forward tcp:${port} -> phone tcp:${port}`);
  } catch (e) {
    log('SYS', `adb forward failed (${(e.stderr || e.message).toString().trim()}). Is the phone plugged in with USB debugging on?`);
  }
}

let n = 1;
const nextId = () => `t${n++}`;
const sentAt = new Map();

function log(kind, text) {
  const t = new Date().toTimeString().slice(0, 8);
  console.log(`${t} ${kind.padEnd(3)} ${text}`);
}

function build(command, a) {
  const id = nextId();
  switch (command) {
    case 'ping': return { v: 1, type: 'ping', id, ts: Date.now() };
    case 'hello': return { v: 1, type: 'hello', id, client: 'bridge-client.mjs' };
    case 'speak': return { v: 1, type: 'speak', id, reply: a[0] || 'repeat' };
    case 'say': return { v: 1, type: 'speak', id, text: a.join(' ') || 'Hello' };
    case 'type-screen': case 'type': return { v: 1, type: 'show_type_screen', id };
    case 'hide-type-screen': case 'hide': return { v: 1, type: 'hide_type_screen', id };
    case 'status': return { v: 1, type: 'get_status', id };
    case 'legacy-say': return { t: 'say', phrase: a[0] || 'repeat' };
    case 'alert': {
      const [label = 'doorbell', dir = 'right', tier = 'medium'] = a;
      const state = label === 'alarm' || label === 'siren' ? 'alarm' : 'cue';
      return { v: 1, type: 'alert', id: `a${Date.now()}`, active: true, state, label, dir, tier };
    }
    case 'alert-end': return { v: 1, type: 'alert', id: alert?.id ?? 'none', active: false };
    case 'raw': return JSON.parse(a.join(' '));
    default: return null;
  }
}

const ws = new WebSocket(url);
let doneWhen = null; // predicate on incoming message that ends a one-shot command

function send(obj) {
  if (obj.type === 'alert') return sendAlert(obj);
  if (obj.id) sentAt.set(obj.id, Date.now());
  const s = JSON.stringify(obj);
  log('OUT', s);
  ws.send(s);
}

// Like the glasses: an active alert is resent every 5 s (the phone times out after 15 s without one).
let alert = null;
let alertTimer = null;
function sendAlert(obj) {
  clearInterval(alertTimer);
  alert = obj.active ? obj : null;
  const out = (o) => { const s = JSON.stringify({ ...o, ts: Date.now() }); log('OUT', s); ws.send(s); };
  out(obj);
  if (alert) alertTimer = setInterval(() => out(alert), 5000);
}

process.on('SIGINT', () => {
  if (alert && ws.readyState === WebSocket.OPEN) {
    sendAlert({ v: 1, type: 'alert', id: alert.id, active: false });
    setTimeout(() => process.exit(0), 300);
  } else process.exit(0);
});

ws.addEventListener('open', () => {
  log('SYS', `connected to ${url}`);
  if (!cmd) return interactive();
  if (cmd === 'listen') return log('SYS', 'listening; Ctrl+C to quit');
  const msg = build(cmd, cmdArgs);
  if (!msg) { log('SYS', `unknown command "${cmd}"`); process.exit(2); }
  send(msg);
  if (cmd === 'ping') doneWhen = (m) => m.type === 'pong' || m.type === 'error';
  else if (cmd === 'speak' || cmd === 'say' || cmd === 'legacy-say') doneWhen = (m) => m.type === 'spoken' || m.type === 'error';
  else if (cmd === 'type-screen' || cmd === 'type') log('SYS', 'waiting for typed text from the phone; Ctrl+C to quit');
  else if (cmd === 'alert') log('SYS', 'phone should be ringing; Ctrl+C ends the alert');
  else doneWhen = (m) => m.type !== 'typing';
  if (doneWhen) setTimeout(() => { log('SYS', 'timed out after 15 s'); process.exit(1); }, 15000);
});

ws.addEventListener('message', (ev) => {
  let m;
  try { m = JSON.parse(ev.data); } catch { log('IN', ev.data); return; }
  const rtt = m.ref && sentAt.has(m.ref) ? `  (${Date.now() - sentAt.get(m.ref)} ms)` : '';
  if (m.type === 'typed_text') {
    log('IN', ev.data);
    console.log(`\n   >>> TYPED TEXT: "${m.text}"\n`);
  } else if (m.type === 'typing') {
    process.stdout.write(`\r         typing: ${m.text.slice(-60).padEnd(60)}`);
    return;
  } else {
    log('IN', ev.data + rtt);
  }
  if (doneWhen && doneWhen(m)) { ws.close(); process.exit(m.type === 'error' ? 1 : 0); }
});

ws.addEventListener('close', (ev) => { log('SYS', `closed (code ${ev.code})`); process.exit(cmd && !doneWhen ? 0 : 1); });
ws.addEventListener('error', () => log('SYS', `could not connect to ${url}. Is the app running? Is the phone plugged in?`));

function interactive() {
  console.log('Commands: ping | hello | speak <type_it|repeat|thanks> | say <text> | type | hide | status | legacy-say <id> |');
  console.log('          alert [label] [dir] [tier] | alert-end | raw <json> | quit');
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: '> ' });
  rl.prompt();
  rl.on('line', (line) => {
    const [c, ...a] = line.trim().split(/\s+/);
    if (!c) return rl.prompt();
    if (c === 'quit' || c === 'exit') { ws.close(); process.exit(0); }
    try {
      const msg = build(c, a);
      if (msg) send(msg); else console.log(`unknown command "${c}"`);
    } catch (e) { console.log(`bad input: ${e.message}`); }
    rl.prompt();
  });
}
