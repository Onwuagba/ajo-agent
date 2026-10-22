"""Frames (with timestamps) -> a constant 30 fps raw video, so marks (epoch seconds) map to video time: t_video = t_mark - t0."""
import json, subprocess, sys, os
W = sys.argv[1]; FF = sys.argv[2]
fr = sorted(json.load(open(f"{W}/frames.json")), key=lambda x: x["t"]); marks = json.load(open(f"{W}/marks.json"))
t0 = fr[0]["t"]
with open(f"{W}/list.txt", "w") as f:
    for i, x in enumerate(fr):
        d = (fr[i + 1]["t"] - x["t"]) if i + 1 < len(fr) else 0.5
        f.write(f"file 'frames/{x['file']}'\nduration {max(d, 0.001):.4f}\n")
    f.write(f"file 'frames/{fr[-1]['file']}'\n")
json.dump({k: round(v - t0, 3) for k, v in marks.items()}, open(f"{W}/vmarks.json", "w"), indent=1)
subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{W}/list.txt", "-vf", "fps=30,scale=1280:720:in_range=pc:out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", f"{W}/raw.mp4"], check=True)
print("duration", round(fr[-1]["t"] - t0, 1))
