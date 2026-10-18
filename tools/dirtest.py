"""Read a server --dump file and print what the G2's direction tag did at each
loud transient (snap, clap, knock), so SIGN and the voting rule in
server/direction.py can be set from data instead of guesses.

    python server/main.py --dump snaps.jsonl     # then snap 5x left, 5x right at 1 m
    python tools/dirtest.py snaps.jsonl

For every peak at least PEAK_X times the median rms, prints the tag on the
frames around it and what side_from_angle would say now.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import direction  # noqa: E402

PEAK_X = 4.0   # a transient is a frame this many times louder than the median
GAP_S = 0.4    # peaks closer than this are the same event
AROUND = 3     # frames to show on each side of the peak


def main(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    rows = [r for r in rows if r.get("direction") is not None]
    if not rows:
        print("no frames with a direction tag")
        return
    med = statistics.median(r["rms"] for r in rows)
    print(f"{len(rows)} frames, median rms {med:.0f}, SIGN={direction.SIGN}, SIDE_DEG={direction.SIDE_DEG}")
    tags = sorted({r["direction"] for r in rows})
    print(f"tag values seen: {tags}")
    peaks = []
    for i, r in enumerate(rows):
        if r["rms"] >= PEAK_X * med and (not peaks or r["t"] - rows[peaks[-1]]["t"] > GAP_S):
            peaks.append(i)
        elif peaks and r["t"] - rows[peaks[-1]]["t"] <= GAP_S and r["rms"] > rows[peaks[-1]]["rms"]:
            peaks[-1] = i
    print(f"{len(peaks)} transients (>= {PEAK_X}x median rms)\n")
    for n, i in enumerate(peaks, 1):
        lo, hi = max(0, i - AROUND), min(len(rows), i + AROUND + 1)
        win = rows[lo:hi]
        cells = []
        for j, r in enumerate(win, lo):
            # * loudest frame; > the frame whose tag the tracker pairs with it
            mark = "*" if j == i else (">" if j == i - direction.TAG_LEAD_FRAMES else " ")
            cells.append(f"{mark}{r['direction']:+4d}@{r['rms']:<5d}")
        tr = direction.DirectionTracker()
        for r in rows[max(0, i - 60): i + 20]:
            tr.add(r["direction"], r["rms"], now=r["t"])
        ang = tr.angle(now=rows[min(i + 19, len(rows) - 1)]["t"])
        print(f"#{n:2d} t={rows[i]['t'] - rows[0]['t']:6.1f}s  " + " ".join(cells)
              + f"   -> tracker {ang:+.0f} = {direction.side_from_angle(ang)}")
    print("\n* = loudest frame, > = the frame whose tag counts for it (TAG_LEAD_FRAMES). Each cell is tag@rms.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "snaps.jsonl")
