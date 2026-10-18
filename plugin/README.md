# Cue glasses app

The Even Hub app. It runs in a WebView inside the Even phone app, turns on the
G2 microphone, forwards every audio frame to the hub over a WebSocket, and
draws whatever state the hub sends back as one line of text on the lenses.
Started from Even's `asr` template; nothing of the template's speech-to-text
remains.

## Run

```bash
npm install
npm run dev                                  # Vite on port 5173
npm run simulate                             # desktop simulator against the dev server
npx evenhub qr --url http://YOUR_LAPTOP_IP:5173   # scan from the Even app to load on real glasses
```

The hub address comes from, in order: `?server=ws://host:8000/ws/glasses` in
the URL, `VITE_SERVER_URL` at build time, or port 8000 on whatever host served
the page. The hub's `http://` and `ws://` origins must also be in
`app.json` under `permissions` → `network` → `whitelist`, exactly, no
wildcards; the Even WebView blocks everything else.

Without a hub: `?demo=1` cycles through every HUD state every 4 s.
`python fake_server.py` is a stand-in hub that sends states and prints what
the glasses send up; `--save recordings/name` also writes the audio to WAV
with a `.jsonl` of each frame's direction tag.

Package for a Beta group: `npm run pack` produces the `.ehpk`. Upload it at
https://evenhub.evenrealities.com, assign it to a Beta group containing your
Even account email, then on the phone: Me, Beta tester, install.

## What is in `src/`

| file | job |
|---|---|
| `main.ts` | startup page, mic on, routes touchpad events, wires everything below |
| `link.ts` | the WebSocket to the hub: audio frames up, state frames down, reconnect after 1 s |
| `hud.ts` | draws a state: one text container, ASCII side arrows, three alert tiers with flashing, centering for the fixed font (`?scale=` and `?line=` to tune on real glasses) |
| `menu.ts` | the on-glasses menu: tap opens, swipe moves, tap cycles a sound off / normal / medium / critical, DONE saves, double-tap cancels |
| `settings.ts` | per-sound choice, kept in `localStorage`; alarm and siren locked to critical |
| `alerts.ts` | tells the Android companion when a critical or medium sound is flashing, so the phone rings (`docs/BRIDGE.md`) |
| `ui.ts` | the phone page: connection status, mic stats, the same per-sound settings, a mirror of what the lenses show |

Touchpad: single tap opens the menu (a long-press on the G2 touchpad opens
Even AI before any plugin sees it). Double-tap on the main page exits through
the system dialog.

## Recordings

`recordings/alarm_1.wav` and `.jsonl` are a real smoke alarm captured through
the G2 with the fake server, the data behind `docs/direction-test.md` and the
alarm thresholds in `server/labels.py`.
