# Earshot bridge: glasses app ⇄ Android companion

Protocol version **1**. Owner: Iurii (`android-companion/`). Change this only
in the group chat, and bump `v` if a change breaks the other side.

The glasses app (in the Even app's web view) tells the Android companion
which reply to speak out loud, or asks it to show the "Please type here"
page. The companion sends back what the hearing person typed.

## 1. How to connect

**Default: the phone hosts the bridge.** The companion runs a WebSocket
server on the same phone as the Even app:

```js
const ws = new WebSocket('ws://127.0.0.1:8765');
```

- Any path is accepted (`/`, `/bridge`, …). Text frames only, one JSON object per frame.
- Add `ws://127.0.0.1:8765` (and `http://127.0.0.1:8765` if the packer
  wants both) to the `network` whitelist in `app.json`. Exact origin; no wildcards.
- Reconnect 1 s after `close`. The companion may restart; your socket will
  drop. Also reconnect on `visibilitychange` back to visible.
- After `open`, send `hello`. The reply tells you the reply ids and their
  current texts.
- 127.0.0.1 is not "local network" under Android 17, so no extra permission
  is needed on either side.

**Fallback: relay through a laptop.** If the web view can't reach
127.0.0.1 (blocked, or the Even app is on a different phone):

1. On a laptop on the same hotspot: `cd android-companion/tools && npm install && node relay.mjs`. It prints the laptop's IP.
2. Glasses app connects to `ws://LAPTOP_IP:8787/glasses` (whitelist that origin).
3. On the companion: **Connection → Connect to a laptop relay**, URL
   `ws://LAPTOP_IP:8787/phone`, **Apply**, and allow **Local network** in the checklist.

Messages are identical in both modes. The relay forwards frames unchanged
and only adds an `error` with `code: "no_phone"` if no phone is connected.

## 2. Envelope

```json
{"v":1, "type":"<type>", "id":"<optional, your choice>", ...fields}
```

- `v`: protocol version, currently `1`. Missing `v` is treated as 1.
- `id`: optional string. Replies about that message carry it back as `ref`,
  so you can match a reply to its request and measure latency.
- Unknown fields are ignored. Unknown `type` gets an `error` reply.

## 3. Glasses → phone

| type | fields | what the phone does | replies |
|---|---|---|---|
| `hello` | `client` (optional) | nothing | `welcome` |
| `ping` | `ts` (optional, your `Date.now()`) | nothing | `pong` |
| `speak` | `reply`: reply id | speaks that reply out loud. `type_it` also opens the type page, unless `"show_type_screen": false` | `ack`, then `spoken` when the audio ends |
| `speak` | `text`: any string | speaks the text (slower: not pre-rendered) | `ack`, then `spoken` |
| `show_type_screen` | | wakes the phone and shows "I'm Deaf. Please type here" over the lock screen | `ack` |
| `hide_type_screen` | | closes the type page | `ack` |
| `get_status` | | nothing | `status` |

Reply ids (texts are editable on the phone; the ids never change):

| id | default text | opens type page |
|---|---|---|
| `type_it` | Hi, I'm Deaf. Could you type what you said on my phone? | yes |
| `repeat` | Sorry, could you repeat that while facing me? | no |
| `thanks` | Thank you! | no |

Also accepted: `deaf_intro` and `type` → `type_it`, `thank_you` → `thanks`,
`"1"`/`"2"`/`"3"` → the three in order. The PLAN.md frame
`{"t":"say","phrase":"repeat"}` also works and behaves like `speak`.

## 4. Phone → glasses

| type | fields | when |
|---|---|---|
| `welcome` | `app`, `app_version`, `protocol`, `replies`: `[{id,label,text,opens_type_screen}]`, `status` | reply to `hello` |
| `pong` | `ref`, `echo_ts` (your `ts`), `ts` (phone time) | reply to `ping` |
| `ack` | `ref`, `ok: true`, `what` | request accepted |
| `spoken` | `ref`, `reply` | the phrase finished playing |
| **`typed_text`** | `id` (`p1`, `p2`, …), `text`, `ts` | the person pressed **Send** on the type page. Show `text` on the HUD. |
| `typing` | `text` | live preview while they type, at most every 300 ms. Optional; ignore it if you like. |
| `status` | `tts` (`ready` or a problem), `audio_allowed` (`true`/`false`/`null`), `type_screen` (`open`/`closed`), `clients` | reply to `get_status`, and pushed whenever the type page opens or closes |
| `error` | `ref`, `code`, `message` | see below |

Error codes: `bad_json`, `missing_field`, `unknown_type`, `unknown_reply`,
`no_phone` (relay only).

`audio_allowed: false` means Android is muting the companion (Android 17
background-audio rule). Fix: open the companion app once.

## 5. Example session

```
→ {"v":1,"type":"hello","id":"g1","client":"earshot-glasses"}
← {"v":1,"type":"welcome","app":"earshot-companion","app_version":"0.1.0","protocol":1,"replies":[{"id":"type_it",...}],"status":{...}}
→ {"v":1,"type":"ping","id":"g2","ts":1760745600123}
← {"v":1,"type":"pong","ref":"g2","echo_ts":1760745600123,"ts":1760745600131}
→ {"v":1,"type":"speak","id":"g3","reply":"type_it"}
← {"v":1,"type":"ack","ref":"g3","ok":true,"what":"speak"}
← {"v":1,"type":"status","tts":"ready","audio_allowed":true,"type_screen":"open","clients":1}
← {"v":1,"type":"spoken","ref":"g3","reply":"type_it"}
← {"v":1,"type":"typing","text":"Where is the"}
← {"v":1,"type":"typed_text","id":"p1","text":"Where is the train station?","ts":1760745612345}
```

## 6. Minimal glasses-side code

```ts
let ws: WebSocket | null = null;
export function connectBridge(onTyped: (text: string) => void) {
  ws = new WebSocket('ws://127.0.0.1:8765');
  ws.onopen = () => ws!.send(JSON.stringify({ v: 1, type: 'hello', client: 'earshot-glasses' }));
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.type === 'typed_text') onTyped(m.text);
  };
  ws.onclose = () => setTimeout(() => connectBridge(onTyped), 1000);
}
export function speakReply(reply: 'type_it' | 'repeat' | 'thanks') {
  ws?.send(JSON.stringify({ v: 1, type: 'speak', id: String(Date.now()), reply }));
}
```

## 7. Testing without the other side

- Without the glasses app: `node android-companion/tools/bridge-client.mjs ping`
  (or open `android-companion/tools/test-client.html`) with the phone plugged in over USB.
- Without the phone: run `node android-companion/tools/relay.mjs` and point the glasses
  app at `ws://LAPTOP_IP:8787/glasses`. The relay logs every frame you send.

## 8. Known risks

- The web view may block `ws://127.0.0.1` from the plugin's origin (Chrome's
  local-network-access rules, or the Even app's whitelist). If `onerror`
  fires immediately while the companion shows "listening", switch to the relay.
- When the phone locks, the Even app may pause the web view, which drops the
  socket. Reconnect on `visibilitychange`. The companion keeps running while locked.
