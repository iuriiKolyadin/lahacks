#!/usr/bin/env node
// Laptop relay for the Cue bridge, for when the Even app's web view
// cannot reach 127.0.0.1 on the phone.
//
//   cd android-companion/tools && npm install && node relay.mjs [--port 8787]
//
//   glasses app (or test client)  ->  ws://LAPTOP_IP:8787/glasses
//   companion app (relay mode)    ->  ws://LAPTOP_IP:8787/phone
//
// Every text frame from a /glasses client goes to every /phone client and
// vice versa, unchanged. The relay never answers anything itself.

import { WebSocketServer } from 'ws';
import os from 'node:os';

const argPort = process.argv.indexOf('--port');
const port = argPort > 0 ? Number(process.argv[argPort + 1]) : 8787;

const wss = new WebSocketServer({ host: '0.0.0.0', port });
const glasses = new Set();
const phones = new Set();

const log = (text) => console.log(`${new Date().toTimeString().slice(0, 8)} ${text}`);

wss.on('connection', (ws, req) => {
  const isPhone = req.url.startsWith('/phone');
  const mine = isPhone ? phones : glasses;
  const others = isPhone ? glasses : phones;
  const name = isPhone ? 'phone' : 'glasses';
  mine.add(ws);
  log(`${name} connected from ${req.socket.remoteAddress} (${glasses.size} glasses, ${phones.size} phone)`);

  ws.on('message', (data, isBinary) => {
    if (isBinary) return;
    const text = data.toString();
    log(`${name} -> ${others.size} ${isPhone ? 'glasses' : 'phone'}: ${text}`);
    if (others.size === 0 && !isPhone) {
      ws.send(JSON.stringify({ v: 1, type: 'error', code: 'no_phone', message: 'Relay has no phone connected' }));
    }
    for (const o of others) if (o.readyState === o.OPEN) o.send(text);
  });
  ws.on('close', () => {
    mine.delete(ws);
    log(`${name} disconnected (${glasses.size} glasses, ${phones.size} phone)`);
  });
});

wss.on('listening', () => {
  log(`relay listening on port ${port}`);
  for (const [ifname, addrs] of Object.entries(os.networkInterfaces())) {
    for (const a of addrs || []) {
      if (a.family === 'IPv4' && !a.internal) {
        log(`  ${ifname}: glasses -> ws://${a.address}:${port}/glasses   phone -> ws://${a.address}:${port}/phone`);
      }
    }
  }
});
