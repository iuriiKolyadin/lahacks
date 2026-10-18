# Test plan: sound alerts on the Android companion

What is being tested: when the glasses flash a sound (tier Critical or Medium),
the Android companion rings like an incoming call. Pressing a reply button on
the phone speaks that phrase out loud. Format: `docs/BRIDGE.md` section 3a.

```
plugin (hud.ts paints a state) -> alerts.ts -> ws /ws/glasses -> server/main.py
    -> ws /ws/pendant -> companion BridgeService -> CallStyle notification + AlertActivity
```

Each layer is tested alone first, with the fakes already in the repo, then
together. Do the levels in order: a failure at one level makes the later ones
meaningless.

## Level 0: laptop only (no phone, no glasses)

Done when writing the change; re-run after any edit to these files.

| # | Check | How | Pass |
|---|---|---|---|
| 0.1 | Plugin type-checks and builds | `cd plugin && npm run build` | no errors |
| 0.2 | Companion builds | `cd android-companion && .\gradlew.bat assembleDebug` | `app-debug.apk` produced |
| 0.3 | Alert feed rules | run `alerts.ts` with a fake `send` (see below) | Normal sends nothing; Medium/Critical send `active:true`; an identical repaint sends nothing; a dir change keeps the id; a new sound gets a new id; idle sends `active:false`; ids never repeat |
| 0.4 | Server relay | `python main.py --mock`, a pendant client on `/ws/pendant`, then `python fake_glasses.py --alert doorbell --seconds 10` | pendant gets the alert, the refresh, then `active:false`; console prints `ALERT` once per change, not on every refresh |
| 0.5 | Late join | connect a second pendant while the alert is active | it gets the alert straight away; after the clear, a new pendant gets nothing |
| 0.6 | `say` still relays | `fake_glasses.py --say repeat` | pendant gets `{"t":"say",...}` unchanged |

0.3 to 0.6 passed on 18 Oct 2026 with throwaway scripts (bundled
`alerts.ts` under Node; a `websockets` client against `main.py --mock`).

## Level 1: phone alone (USB, no server, no glasses)

Install the new APK, open the app once, and clear every ❌ in the checklist,
including the new **Sound-alert calls on**. Use the **Sound alerts** buttons
in the app, or over USB `node tools/bridge-client.mjs alert <label> <dir> <tier>`
(Ctrl+C ends the alert). Watch `adb logcat -s Cue`.

| # | Setup | Action | Pass |
|---|---|---|---|
| 1.1 | Phone unlocked, in the app | **Test alert: Doorbell on your right** | Alert page opens: "Doorbell", "On your right", orange band flashing slowly, phone vibrating slowly |
| 1.2 | Phone unlocked, on the home screen | `bridge-client.mjs alert doorbell right medium` | Heads-up call notification with "Doorbell" as the caller, **Decline** and **Answer** buttons; one vibration burst; no sound |
| 1.3 | As 1.2 | **Answer** | Alert page opens **without** vibrating; reply buttons work |
| 1.4 | As 1.2 | **Decline** | Notification gone; refreshes every 5 s do not bring it back; log says `alert dismissed on the phone` |
| 1.5 | Screen off, locked | **Test alert in 5 s: Smoke alarm**, lock at once | Screen wakes, page shows over the lock screen without unlocking, red band flashing fast, vibration fast and continuous |
| 1.6 | As 1.5 | Press **Repeat** | Phone says the Repeat phrase out loud while still locked; vibration and flashing stop; page stays open; "Speaking: …" shows |
| 1.7 | As 1.5 | Press **Please type** | Phrase is spoken and the "Please type here" page opens on top |
| 1.8 | Alert page open, untouched | **End test alert** (or Ctrl+C on the client) | "The sound has stopped", flashing stops, page closes about 8 s later |
| 1.9 | Alert page open, a reply pressed | End the alert | Page says stopped and stays open until Dismiss or Back |
| 1.10 | Test alert from the app button (never refreshed) | Wait | Alert ends about 15 s later, log says `no update from the glasses for 15 s` |
| 1.11 | `bridge-client` interactive: `alert doorbell right`, then `alert doorbell left` within 5 s | | Second frame has a new id (the client makes one per command), so the phone rings again. To check the silent dir update, use `raw` with the same id and a new `dir`: the page text changes and nothing re-rings |
| 1.12 | Active doorbell | `alert alarm behind critical` | Siren replaces doorbell, phone rings again at the critical rhythm |
| 1.13 | **Ring like a call** unticked | any test alert | Nothing rings; status line shows the alert with "ringing OFF" |
| 1.14 | "Full-screen page over lock screen" turned **off** in Settings | test alert, locked | Plain heads-up with **Dismiss** / **Reply**, no full-screen page; log has the "Full-screen intent not allowed" error. Turn it back on after |
| 1.15 | Do Not Disturb on | critical test alert, locked | Record what happens. The notification may be held back by DND; the page's vibration uses alarm usage. Write the result here |
| 1.16 | Phone locked 5 min, then a test alert over USB | | Same as 1.5, and the phrase is audible ("Audio while locked: allowed") |

## Level 2: server to phone (laptop + phone, no glasses)

Laptop and phone on the same hotspot. On the phone: **Connection → Connect to
a laptop**, `ws://LAPTOP_IP:8000/ws/pendant`, **Apply**, allow **Local network**.

| # | Action | Pass |
|---|---|---|
| 2.1 | `python main.py` | console shows `pendant connected`; phone status `connected to relay`, clients 1 |
| 2.2 | `python fake_glasses.py --alert doorbell --seconds 20` | phone rings within 1 s; ends about 20 s later when the script clears it |
| 2.3 | `fake_glasses.py --alert siren --alert-tier critical`, then Ctrl+C the script (no clear sent) | phone ends the alert by itself about 15 s after the last refresh |
| 2.4 | Start an alert, **then** reconnect the phone (Apply and restart bridge) | phone rings as soon as it reconnects (server replay) |
| 2.5 | Restart `main.py` while the phone is connected | phone reconnects by itself within about 2 s (status cycles through reconnecting) |
| 2.6 | `fake_glasses.py --say repeat` | phone speaks the Repeat phrase (existing path still works) |

## Level 3: plugin to phone (no glasses, no classifier)

`python main.py --mock` cycles: idle, doorbell (Medium, 4 s), speech (Normal),
name (Medium, 4 s), siren (Critical, held), every 5 s. Run the plugin in the
simulator: `cd plugin && npm run dev`, then `npm run simulate`. If the simulator
cannot reach the server, add `?server=ws://127.0.0.1:8000/ws/glasses`.

| # | Expect on the phone, per 25 s cycle | Pass |
|---|---|---|
| 3.1 | Doorbell rings; ends about 4 s later | yes |
| 3.2 | Speech: nothing (Normal) | yes |
| 3.3 | Name rings as "Someone said your name"; ends about 4 s later | yes |
| 3.4 | Siren rings at the critical rhythm; ends at the next idle | yes |
| 3.5 | On the plugin page, set Doorbell to **Normal** | doorbell no longer rings; set it back to Medium and it rings again |
| 3.6 | Change Doorbell's tier **while** it is showing | Normal: the phone alert ends at once. Critical: the phone updates without re-ringing |
| 3.7 | Close the plugin while the siren shows | phone alert ends (cleanup sends the clear) |

## Level 4: everything, on the real glasses

The full setup from the main README (glasses phone, server laptop,
classifier iPhone), plus the companion connected as in level 2.

| # | Action | Pass |
|---|---|---|
| 4.1 | Doorbell clip from a phone, 1 m to the right | glasses flash `DOORBELL ----->`; companion rings "Doorbell, On your right" |
| 4.2 | Latency: film the lenses and the companion together | phone rings within 1 s of the glasses' first flash, 5 runs out of 5 |
| 4.3 | Smoke alarm clip with the companion locked in a pocket | the vibration is felt; taking the phone out shows the page over the lock screen |
| 4.4 | Someone talks next to the wearer | glasses show `speech`; phone stays quiet |
| 4.5 | Doorbell, then press **Please type** on the phone | the visitor hears the phrase and gets the type page |
| 4.6 | Lock the glasses phone 5 min, reopen the plugin, play a doorbell | glasses and companion both alert |
| 4.7 | 10 min of normal room noise | no false calls on the phone that did not also show on the glasses |

## Known limits (by design, not bugs)

- Through the server, the phone's replies (`typed_text`, `spoken`) do not reach
  the glasses: `/ws/pendant` input is ignored. Use the direct 127.0.0.1 bridge
  for typed text.
- Dismissing on the phone does not clear the glasses.
- The call buttons are labelled **Answer** and **Decline** by Android
  (CallStyle); they open the reply page and dismiss.
- Without the full-screen-intent permission, alerts fall back to a heads-up
  notification (test 1.14).
