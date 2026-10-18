# Earshot glasses app

The Even Hub app that runs on the phone and draws on the G2 glasses. It
listens through the glasses' microphone, recognises sounds with Google's YAMNet
model (running on the phone itself, no laptop or internet needed), and shows
one short line on the lenses when something matters.

Status: **milestone 0**: "hello" on the glasses, plus hardware checks (model
loads on the phone, microphone works, direction data).

---

## One-time setup (laptop)

You need Node.js (already installed on this laptop) and Chrome.

1. Open a terminal in VS Code (menu **Terminal → New Terminal**).
2. Type these and press Enter after each:
   ```
   cd glasses-app
   npm install
   ```
   It takes about 30 seconds and ends with something like `added 76 packages`.

## Check the model works on the laptop (no glasses)

```
npm run check
```

It builds the app, opens it in an invisible Chrome window and prints the app's
log. The last line should look like:

```
[model] self-test top: Beep, bleep 0.74, ...
```

If it says `FAILED`, copy the output and send it to whoever is helping you.

## Load it onto the glasses (milestone 0 test)

### Before the first time only

- **Developer mode on the phone.** On the laptop, sign in at
  https://hub.evenrealities.com/login with the *same* account the Even app on
  the phone uses. Then on the phone, fully close the Even Realities app (swipe
  it away from recent apps) and open it again. In the **Even Hub** tab you
  should now see a developer section with a **Scan QR** button in the top
  right.
- **Same network.** Turn on the Pixel's hotspot. Connect the laptop to it. The
  phone with the Even app must be on the same hotspot (if the Pixel is both the
  hotspot and the Even phone, that's automatic).
- **Tell Windows the hotspot is a private network.** On the laptop: Settings →
  Network & internet → Wi-Fi → click the hotspot's name → *Network profile
  type* → **Private**. (New networks start as Public, and the firewall would
  then block the phone.)

### Every time

1. Put the glasses on, or set them where you can see the lenses. Make sure they
   are connected to the Even app.
2. In the VS Code terminal (inside `glasses-app`), run:
   ```
   npm run phone
   ```
3. **The first time only, a Windows Security window pops up** saying "Windows
   Defender Firewall has blocked some features of Node.js". Tick **Private
   networks**, untick Public, and click **Allow access**. (If you don't see it,
   it may be hidden behind VS Code. Check the taskbar.)
4. The terminal prints the laptop's address (`<- using this one`) and then a
   big square QR code made of blocks.
5. On the phone: Even app → **Even Hub** tab → **Scan QR** (top right) → point
   the camera at the QR code on the laptop screen.
6. **What you should see on the glasses**, within a few seconds:
   ```
   hello

   model OK: load 900 ms, run 80 ms
     heard "Beep, bleep" 0.74
   mic: 16000 samples/s, 10 frames/s
     direction: always null
   ```
   The numbers will differ. What matters:
   - `hello` appears → the app runs on the glasses.
   - `model OK` → the sound model works on the phone. `model FAILED` means it
     doesn't; send a photo of the lenses.
   - `mic: 16000 samples/s` → the glasses mic is streaming. `mic: no audio yet`
     after 10 seconds means it isn't.
   - `direction:` shows numbers → the glasses give us direction (good news for
     R7). `always null` → they don't.
7. Speak, then stay silent, and watch whether the direction numbers change
   when someone talks from your left vs your right. Write down what you see.
8. **Double-tap** a temple. The system's "exit app?" dialog should appear.
   Confirm to close.

The phone screen also shows the same text plus a scrolling log. A photo of
the phone screen is the easiest way to send results back.

### If something goes wrong

| What you see | What to do |
|---|---|
| Phone says it can't connect after scanning | Firewall: check the hotspot is **Private** (above), then run `npm run phone` again. |
| Terminal shows several addresses and the phone can't connect | Run `npm run phone -- 10.x.x.x` with the address that starts like the phone's hotspot address (often `10.` or `192.168.`). |
| QR code is too big or garbled to scan | Run `npx evenhub qr -e --url http://ADDRESS:5173` in a second terminal; it opens the QR as a picture. |
| Glasses go blank after the phone locks | Normal for this test mode. Scan the QR again. (Beta builds survive locking; that's milestone 3.) |
| Stop the app on the laptop | Click in the terminal and press **Ctrl+C**. |

## Package for the Beta group

```
npm run pack
```

Produces `earshot.ehpk` (about 5.3 MB; Even's practical limit is about 10 MB).
Full upload steps come in milestone 3.

## How it's built

| File | What it does |
|---|---|
| `app.json` | App manifest: name Earshot, id `com.earshot.lahacks.dev`, glasses mic permission. No network permission: nothing is sent anywhere. |
| `src/main.ts` | Startup, glasses page, taps, mic. |
| `src/bridge.ts` | Connects to the Even app, or runs in "browser mode" on a laptop. |
| `src/classify/` | The classifier interface and the YAMNet (MediaPipe) backend. |
| `src/log.ts` | The log you see on the phone and in `npm run check`. |
| `scripts/fetch-model.mjs` | Downloads `yamnet.tflite` and copies the WASM runtime into `public/` (runs automatically). |
| `scripts/phone.mjs` | `npm run phone`: dev server + QR code. |
| `scripts/check.mjs` | `npm run check`: runs the app in headless Chrome and prints its log. |
