# Cue Companion (Android)

The phone half of Cue's "answer for me" feature. When the wearer picks a
reply on the glasses, this app:

1. Speaks it out loud through the phone speaker, even with the phone locked.
2. For "please type", wakes the screen and shows **I'm Deaf. Please type here**
   over the lock screen, without unlocking.
3. Sends what the other person typed back to the glasses.

It also rings like an incoming call when the glasses flash an urgent sound
(every sound set to Critical or Medium on the plugin page). The ring is a
call-style notification. When the phone is locked, a full-screen page shows
what the sound is, where it came from, and one big button per phrase, so the
wearer can answer out loud from the phone.

The glasses app talks to it over a WebSocket. The message format is in
[`docs/BRIDGE.md`](../docs/BRIDGE.md).

Targets Android 17 (API 37). Built and tested on a Pixel 10 Pro. Works on Android 13+.

---

## One-time setup

### Laptop

You need a JDK 17 or newer and the Android SDK. The simplest route on any OS
is to install Android Studio, which brings both, open the `android-companion`
folder, let it sync, and press Run with the phone plugged in. Everything
below is the command-line equivalent.

`local.properties` (not committed) tells Gradle where the SDK is. If it is
missing, create `android-companion/local.properties` with one line:
```
sdk.dir=/path/to/Android/Sdk
```
On Windows that is `sdk.dir=C\:\\Users\\YOU\\AppData\\Local\\Android\\Sdk`;
on macOS, `sdk.dir=/Users/YOU/Library/Android/sdk`.

Node.js 22 or newer is needed only for the test tools in `tools/`.

### Phone (Pixel)

1. **Developer options:** Settings → About phone → tap **Build number** 7
   times → enter your PIN. It says "You are now a developer".
2. **USB debugging:** Settings → System → Developer options → turn on
   **USB debugging** → OK.
3. Plug the phone into the laptop with a USB-C cable. On the phone, tap
   **Allow** on "Allow USB debugging?" (tick "Always allow from this computer").
   If the phone asks what the USB connection is for, pick **File transfer**.

---

## Build and install

With the phone plugged in and USB debugging allowed:

```bash
cd android-companion
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

On Windows, in PowerShell, the same three steps are `.\gradlew.bat
assembleDebug` and `adb.exe` from `%LOCALAPPDATA%\Android\Sdk\platform-tools`.
If Gradle cannot find a JDK, set `JAVA_HOME` to one first (for example
`$env:JAVA_HOME = "$env:USERPROFILE\.jdks\jdk-21.0.12.1+1"` on the laptop this
was built on).

Then open **Cue Companion** on the phone.

Logs: `adb logcat -s Earshot` shows every message in and out (the log tag
kept the app's original name).

## First run on the phone

Open the app. Under **Permissions checklist**, tap the button next to every
red ❌ until all are ✅:

| Item | What you tap |
|---|---|
| Notifications allowed | **Allow** → Allow |
| Sound-alert calls on | **Open** → make sure the channel is on (it is by default) |
| Full-screen page over lock screen | **Allow** → turn the switch on → back (type page and sound alerts) |
| Battery: unrestricted | **Allow** → Allow |
| Local network | **Allow** → Allow (needed only for the laptop relay) |

The app never changes the volume. Set the phone's media volume yourself
before a demo.

Keep the app opened from its icon at least once after every install or
reboot. Android 17 only lets it speak while locked if its service was
started from the app's screen.

Lock-screen notifications must be on: Settings → Notifications → Notifications
on lock screen → **Show conversations, default, and silent**.

## Test without the glasses

With the phone plugged in over USB:

```powershell
cd android-companion\tools
node bridge-client.mjs ping                 # expect: pong
node bridge-client.mjs speak repeat         # phone says "Sorry, could you repeat that…"
node bridge-client.mjs type-screen          # phone shows the type page; typed text prints here
node bridge-client.mjs alert alarm behind critical   # phone rings with a sound alert; Ctrl+C ends it
node bridge-client.mjs                      # interactive: type ping, speak thanks, type, …
```

The client runs `adb forward tcp:8765 tcp:8765` for you, so the laptop's
127.0.0.1:8765 reaches the phone over USB.

Prefer buttons? Run `adb forward tcp:8765 tcp:8765`, then open
`tools/test-client.html` in Chrome and press **Connect**.

The app's **Sound alerts** section has the same test with buttons, including one
that rings 5 s later so you can lock the phone first.

## Sound alerts from the glasses (Cue server)

The alerts come from the plugin, through `server/main.py`. On the phone:
**Connection → Connect to a laptop (Cue server or relay)**, URL
`ws://SERVER_IP:8000/ws/pendant`, **Apply and restart bridge**, and allow
**Local network**. The server console prints `pendant connected`, then an
`ALERT` line for each sound. Spoken replies (`say` from the glasses) arrive on
the same connection. Test plan: [`docs/alerts-test-plan.md`](../docs/alerts-test-plan.md).

## Laptop relay (if the glasses app can't reach 127.0.0.1)

```powershell
cd android-companion\tools
npm install
node relay.mjs                              # prints ws://LAPTOP_IP:8787/glasses and /phone
```

On the phone: **Connection → Connect to a laptop relay**, URL
`ws://LAPTOP_IP:8787/phone`, **Apply and restart bridge**. Point the glasses
app (or `node bridge-client.mjs --url ws://127.0.0.1:8787/glasses --no-adb ping`)
at the `/glasses` URL.

## How it works

| File | Job |
|---|---|
| `BridgeService.kt` | Foreground service: hosts the bridge, handles messages, holds a wake lock |
| `Transports.kt` | WebSocket server on the phone, or client to the laptop relay (Java-WebSocket library) |
| `Speaker.kt` | Text-to-speech. Each phrase is rendered to a WAV once, so replies play instantly |
| `Notifications.kt` | Lock-screen notification with Speak buttons (the fallback), and the full-screen "type" alert |
| `TypeActivity.kt` | The "I'm Deaf. Please type here" page, shown over the lock screen |
| `Alerts.kt` | The current sound alert, parsed from `alert` frames |
| `AlertActivity.kt` | The "incoming call" page for a sound alert: flashes, vibrates, one button per phrase |
| `MainActivity.kt` | Debug panel: status, message log, test buttons, permissions, settings |
| `tools/` | `bridge-client.mjs` (CLI tester), `test-client.html` (browser tester), `relay.mjs` (laptop relay) |

Android rules this follows, checked October 2026:

- **Background audio (Android 17):** playback from the background is silently
  muted unless the foreground service was started while the app was visible.
  The app starts its service from the main screen and reports "Audio while
  locked: BLOCKED" if Android refuses.
- **Full-screen intents (Android 14+):** only allowed if the user grants
  them. The checklist links to that setting. Without it you get a heads-up
  notification instead.
- **Local network (Android 17):** the `ACCESS_LOCAL_NETWORK` permission is
  needed for Wi-Fi/LAN connections (relay mode). 127.0.0.1 is not covered.
- **Foreground service type:** `specialUse`, which has no time limit.

## Troubleshooting

| Problem | Fix |
|---|---|
| `adb devices` lists nothing | Replug the cable, unlock the phone, accept the USB debugging prompt. Try another cable/port. |
| `adb devices` says `unauthorized` | Unlock the phone and tap **Allow** on the prompt. |
| Silent while locked | Open the app (re-arms audio), turn up the media volume with the volume buttons, check the status says "Audio while locked: allowed". |
| Type page doesn't appear when locked | Checklist: "Full-screen page over lock screen" must be ✅. |
| No sound alerts | Status must say "Bridge connected to relay" with the `/ws/pendant` URL; server console must show `pendant connected`. The sound must be Critical or Medium on the plugin page. |
| Alert shows as a plain notification, not a call | "Full-screen page over lock screen" is ❌; the app falls back to a heads-up with Dismiss / Reply. |
| Notification buttons not on lock screen | Pull down on the Cue notification to expand it. Check lock-screen notification settings above. |
