# Earshot Companion (Android)

The phone half of Earshot's "answer for me" feature. When the wearer picks a
reply on the glasses, this app:

1. Speaks it out loud through the phone speaker, even with the phone locked.
2. For "please type", wakes the screen and shows **I'm Deaf. Please type here**
   over the lock screen, without unlocking.
3. Sends what the other person typed back to the glasses.

The glasses app talks to it over a WebSocket. The message format is in
[`docs/BRIDGE.md`](../docs/BRIDGE.md).

Targets Android 17 (API 37). Built and tested on a Pixel 10 Pro. Works on Android 13+.

---

## One-time setup

### Laptop (Windows)

You need a JDK 17+ and the Android SDK. Either install Android Studio (it
brings both), or use what's already on this laptop:

- JDK: `%USERPROFILE%\.jdks\jdk-21.0.12.1+1`
- Android SDK: `%LOCALAPPDATA%\Android\Sdk`

`local.properties` (not committed) points Gradle at the SDK. If it's
missing, create `android-companion/local.properties` containing:
```
sdk.dir=C\:\\Users\\YOU\\AppData\\Local\\Android\\Sdk
```

Node.js 22+ is needed only for the test tools.

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

In a VS Code terminal (PowerShell):

```powershell
cd android-companion
$env:JAVA_HOME = "$env:USERPROFILE\.jdks\jdk-21.0.12.1+1"
.\gradlew.bat assembleDebug
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r app\build\outputs\apk\debug\app-debug.apk
```

Then open **Earshot Companion** on the phone.

Logs: `adb logcat -s Earshot` shows every message in and out.

## First run on the phone

Open the app. Under **Permissions checklist**, tap the button next to every
red ❌ until all are ✅:

| Item | What you tap |
|---|---|
| Notifications allowed | **Allow** → Allow |
| Full-screen page over lock screen | **Allow** → turn the switch on → back |
| Battery: unrestricted | **Allow** → Allow |
| Local network | **Allow** → Allow (needed only for the laptop relay) |
| Media volume loud | **Max** |

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
node bridge-client.mjs                      # interactive: type ping, speak thanks, type, …
```

The client runs `adb forward tcp:8765 tcp:8765` for you, so the laptop's
127.0.0.1:8765 reaches the phone over USB.

Prefer buttons? Run `adb forward tcp:8765 tcp:8765`, then open
`tools/test-client.html` in Chrome and press **Connect**.

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
| Silent while locked | Open the app (re-arms audio), check volume, check the status says "Audio while locked: allowed". |
| Type page doesn't appear when locked | Checklist: "Full-screen page over lock screen" must be ✅. |
| Notification buttons not on lock screen | Pull down on the Earshot notification to expand it. Check lock-screen notification settings above. |
