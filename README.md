# Earshot

Sound awareness for deaf and hard-of-hearing people, on Even Realities G2
smart glasses. The glasses stay blank. When a sound you cannot hear matters,
a doorbell, a knock, a siren, an alarm, or your own name, one line appears in
your line of sight saying what it was and which way it came from. When you
need to answer a hearing person, a long-press on the glasses makes a pendant
speak for you.

Built at the LA Hacks AI Hackathon, 17 to 18 October 2026, for the Beyond the
Digital track and the Even Realities challenge.

## Read these

- `PRD.md`: what we are building and why, the demo script, requirements.
- `PLAN.md`: how it is built, who builds what, message formats, checkpoints.
- `docs/RESEARCH.md`: what Even Realities has, what the SDK gives us, prior
  art, and what Earshot adds.

## Layout

| Folder | What | Owner |
|---|---|---|
| `plugin/` | the Even Hub app that runs on the phone and draws on the glasses | Wendy |
| `server/` | Python server: YAMNet sound classifier, Porcupine name spotter, state machine | Nikhil |
| `pendant/` | Android app worn on a lanyard that speaks a phrase when the wearer long-presses | Iurii |
| `tools/` | recording and evaluation scripts | Dara |
| `docs/` | research and test results | everyone |

## Run it

See `PLAN.md` section 4 for setup and section 3 for the message formats. In
short: `python server/main.py` on one laptop, the plugin and the pendant
app both pointed at that laptop's IP.

## Install and run on G2

Filled in before submission. Will cover: packaging with `evenhub pack`,
the Beta group, the network whitelist, and the one key needed
(`PICOVOICE_KEY` for the name spotter).
