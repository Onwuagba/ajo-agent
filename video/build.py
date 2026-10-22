"""Assemble the Ajo demo: Kokoro voiceover + HTML graphics + procedural music over the real footage.
usage: python build.py WORKDIR FFMPEG OUT.mp4   (needs raw.mp4 in WORKDIR; node + puppeteer-core for graphics)"""
import hashlib, json, os, subprocess, sys
import numpy as np, soundfile as sf

W, FF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SR = 24000
os.makedirs(f"{W}/seg", exist_ok=True); os.makedirs(f"{W}/voice", exist_ok=True); os.makedirs(f"{W}/gfx", exist_ok=True)
sh = lambda *a: subprocess.run(a, check=True, capture_output=True)

# (raw start, raw end, speed, caption, cue)
SEGS = [
    (1.6, 13.0, 1.0, "Sign up", "Maya signs up and opens her first savings circle."),
    (13.1, 32.0, 2.0, "Create the circle", "She names it, sets fifty dollars a week, and invites two friends with one-use links."),
    (32.2, 60.0, 2.6, "Friends join", "Ola and Kemi join from their own links, each with their own account."),
    (60.0, 69.0, 1.0, "Rules in plain English", "Maya writes the rules the way she'd say them out loud."),
    (69.0, 85.4, 4.0, "The model reads the rules", "A model turns them into structured rules. Code then checks every limit for conflicts."),
    (85.4, 95.3, 1.0, "Appoint the treasurer", "No conflicts. She appoints the treasurer, which now works only inside those rules."),
    (95.3, 126.4, 3.0, "Everyone approves their own PayPal", "Each member approves their own PayPal subscription. Nothing starts until all three have."),
    (126.4, 140.0, 1.6, "The circle is live", "The circle is live. Cycle one is open."),
    (140.0, 156.0, 2.8, "Ask in your own words", "Ola asks to skip this week, in her own words. The model reads it, and the rules engine checks it."),
    (156.0, 162.5, 1.0, "Try to talk it round", "Then she tries to talk the treasurer into paying her the whole pot. Blocked, and logged, before any model sees it."),
    (162.5, 181.9, 2.2, "A human approves", "Her skip needs Maya's approval. The pot drops to a hundred dollars."),
    (181.9, 204.9, 2.2, "A missed payment", "Kemi misses a payment. After the grace period the treasurer invoices her through PayPal, and the cycle closes."),
    (204.9, 226.2, 2.6, "Hardship repayments", "Ola's skipped payment comes back as scheduled repayments, invoiced automatically."),
    (226.2, 243.0, 1.7, "Payouts need approval", "When a cycle is funded, the treasurer proposes the payout, and the people who need to agree approve it."),
    (243.0, 247.8, 1.0, "Members", "Everyone can see who has paid and who is next."),
    (247.8, 272.7, 1.9, "Tamper-evident audit", "Every action sits in a hash-chained audit trail. Change one row, and verification breaks."),
]
TITLE = ("Ajo", "A savings circle with an <em>AI treasurer</em>", "AI interprets. Code enforces.", 4.0)
CLOSE_CUE = "Ajo. The model reads the request. The rules decide."
CLOSE_STATS = ["3 members, 3 cycles", "model reads, code enforces", "hash-chained audit", "PayPal sandbox"]

# ---------- auth-screen detection: sign-in/landing frames are dead time, so they get sped up ----------
RAWV = np.frombuffer(subprocess.run([FF, "-v", "error", "-i", f"{W}/raw.mp4", "-vf", "fps=4,scale=32:18", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout, "uint8").reshape(-1, 18, 32, 3)
AUTH = (RAWV[:, :, :10, 1].astype(int).mean(axis=(1, 2)) > 45) & (RAWV[:, :, :10, 1].astype(int).mean(axis=(1, 2)) - RAWV[:, :, :10, 0].astype(int).mean(axis=(1, 2)) > 25)
def subs(a, b, sp):
    if a == SEGS[0][0]: return [(a, b, sp)]  # the sign-up form is the point of the first scene
    out, t0 = [], a
    while t0 < b - 1e-6:
        k = int(t0 * 4); au = bool(AUTH[min(k, len(AUTH) - 1)]); t1 = t0
        while t1 < b - 1e-6 and bool(AUTH[min(int(t1 * 4), len(AUTH) - 1)]) == au: t1 += 0.25
        t1 = min(t1, b); out.append((t0, t1, max(sp, 6.0) if au else sp)); t0 = t1
    return out
sub_dur = lambda a, b, sp: sum((y - x) / v for x, y, v in subs(a, b, sp))

# ---------- voice (Kokoro af_heart, cached) ----------
from kokoro_onnx import Kokoro
from kokoro_onnx.config import EspeakConfig
K = Kokoro(f"{W}/kokoro-v1.0.onnx", f"{W}/voices-v1.0.bin", espeak_config=EspeakConfig(lib_path="/usr/local/lib/libespeak-ng.dylib", data_path="/usr/local/share/espeak-ng-data"))
def voice(text, speed=1.0):
    p = f"{W}/voice/{hashlib.md5((text+str(speed)).encode()).hexdigest()}.wav"
    if not os.path.exists(p):
        a, sr = K.create(text, voice="af_heart", speed=speed, lang="en-us"); sf.write(p, a, sr)
    a, _ = sf.read(p); return a.astype("float32")
cues = [voice(s[4]) for s in SEGS]
title_cue = voice("Meet Ajo. A savings circle, run by an A I treasurer.")
close_cue = voice(CLOSE_CUE)
# a cue that is too long for its segment gets a gently faster read (cap 1.3), else the footage is held
def fit(i):
    raw = sub_dur(*SEGS[i][:3]); d = len(cues[i]) / SR + 0.7
    if d > raw and d / raw < 1.3: cues[i] = voice(SEGS[i][4], min(1.3, d / raw)); d = len(cues[i]) / SR + 0.7
    return max(raw, d)
durs = [fit(i) for i in range(len(SEGS))]

# ---------- graphics (HTML -> PNG, 1600x900) ----------
CSS = """*{box-sizing:border-box;margin:0}body{width:1600px;height:900px;font-family:'Helvetica Neue',Arial,sans-serif;color:#eaf5ef;
background:radial-gradient(1200px 700px at 30% 20%,#14382c 0%,#0a1a15 55%,#050d0a 100%);position:relative;overflow:hidden}
.grid{position:absolute;inset:0;background-image:linear-gradient(#ffffff08 1px,transparent 1px),linear-gradient(90deg,#ffffff08 1px,transparent 1px);background-size:64px 64px}
.c{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:0 120px}
h1{font-size:118px;font-weight:800;letter-spacing:-3px;line-height:1.05}em{font-style:normal;background:linear-gradient(90deg,#4fe3a8,#f1c24b);-webkit-background-clip:text;color:transparent}
.sub{font-size:40px;color:#b9d6c8;margin-top:26px}.pill{margin-top:38px;padding:14px 30px;border:2px solid #4fe3a855;border-radius:40px;font-size:30px;color:#4fe3a8;background:#4fe3a812}
.badge{position:absolute;left:48px;bottom:40px;font-size:24px;color:#8fb3a3;letter-spacing:1px}
.chips{display:flex;gap:18px;margin-top:44px;flex-wrap:wrap;justify-content:center}.chip{padding:16px 28px;border-radius:14px;background:#ffffff10;border:1px solid #ffffff22;font-size:30px}"""
def card(name, body): open(f"{W}/gfx/{name}.html", "w").write(f"<style>{CSS}</style><div class=grid></div>{body}")
card("title", f"<div class=c><h1>Aj<em>o</em></h1><div class=sub>{TITLE[1]}</div><div class=pill>{TITLE[2]}</div></div><div class=badge>Built for the PayPal AI Hackathon</div>")
card("close", f"<div class=c><h1>The model reads. <em>The rules decide.</em></h1><div class=chips>{''.join(f'<div class=chip>{c}</div>' for c in CLOSE_STATS)}</div></div><div class=badge>Ajo · open source · PayPal sandbox</div>")
for i, s in enumerate(SEGS):
    open(f"{W}/gfx/cap{i}.html", "w").write(f"<style>body{{margin:0;width:1600px;height:900px;background:transparent;font-family:'Helvetica Neue',Arial,sans-serif}}"
        f".p{{position:absolute;left:48px;bottom:44px;padding:14px 28px;border-radius:40px;background:#0a1a15dd;border:2px solid #4fe3a866;color:#eaf5ef;font-size:32px;font-weight:600}}</style><div class=p>{s[3]}</div>")
gjs = f"""import {{createRequire}} from 'module';const require=createRequire('/Users/kene/Documents/projects/Moi/Hackathon/hackathon-scaffolds/firetv-learning-games/package.json');
const p=require('puppeteer-core');const fs=require('fs');const W={json.dumps(W)};
const b=await p.launch({{executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:'new',timeout:90000}});
const pg=await b.newPage();await pg.setViewport({{width:1600,height:900,deviceScaleFactor:1}});
for(const f of fs.readdirSync(W+'/gfx').filter(f=>f.endsWith('.html'))){{await pg.goto('file://'+W+'/gfx/'+f);await pg.screenshot({{path:W+'/gfx/'+f.replace('.html','.png'),omitBackground:true}});}}
await b.close();"""
open(f"{W}/gfx/shots.mjs", "w").write(gjs)
sh("node", f"{W}/gfx/shots.mjs")

# ---------- video edit ----------
GRADE = "scale=1600:900:flags=lanczos,vignette=PI/8,eq=contrast=1.05:saturation=1.08:brightness=0.01,setsar=1,format=yuv420p"
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p", "-r", "30", "-an"]
parts, starts, t = [], [], 0.0
def still(name, dur, zoom):  # Ken-Burns push-in on a graphic
    out = f"{W}/seg/{name}.mp4"
    sh(FF, "-y", "-loop", "1", "-t", str(dur), "-i", f"{W}/gfx/{name}.png", "-vf",
       f"scale=3200:1800,zoompan=z='1+{zoom}*on/{int(dur*30)}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1600x900:fps=30,fade=t=in:d=0.5,fade=t=out:st={dur-0.5}:d=0.5,setsar=1,format=yuv420p", *ENC, out)
    return out
title_dur = max(TITLE[3], len(title_cue) / SR + 1.2)
parts.append(still("title", title_dur, 0.06)); starts.append(0.0); t += title_dur
for i, (a, b, sp, cap, _) in enumerate(SEGS):
    out = f"{W}/seg/s{i}.mp4"; d = durs[i]; pad = max(0.0, d - sub_dur(a, b, sp)); ss = subs(a, b, sp)
    chain = "".join(f"[0:v]trim={x:.3f}:{y:.3f},setpts=(PTS-STARTPTS)/{v}[c{j}];" for j, (x, y, v) in enumerate(ss)) + "".join(f"[c{j}]" for j in range(len(ss))) + f"concat=n={len(ss)}:v=1:a=0,"
    fc = (chain + f"{GRADE},tpad=stop_mode=clone:stop_duration={pad:.3f},trim=0:{d:.3f}[v];"
          f"[1:v]format=rgba,fade=t=in:st=0.3:d=0.35:alpha=1,fade=t=out:st={max(0.4, d-0.7):.2f}:d=0.35:alpha=1[o];[v][o]overlay=0:0,format=yuv420p[x]")
    sh(FF, "-y", "-i", f"{W}/raw.mp4", "-loop", "1", "-t", f"{d:.3f}", "-i", f"{W}/gfx/cap{i}.png", "-filter_complex", fc, "-map", "[x]", *ENC, out)
    parts.append(out); starts.append(t); t += d
close_dur = max(5.0, len(close_cue) / SR + 1.6)
parts.append(still("close", close_dur, 0.05)); starts.append(t); t += close_dur
TOTAL = t
open(f"{W}/seg/list.txt", "w").write("".join(f"file '{p}'\n" for p in parts))
sh(FF, "-y", "-f", "concat", "-safe", "0", "-i", f"{W}/seg/list.txt", *ENC, f"{W}/video_only.mp4")

# ---------- audio: voice + music + sfx with ducking ----------
N = int(TOTAL * SR) + SR; rng = np.random.default_rng(7)
vo = np.zeros(N, "float32")
def put(buf, a, at): i = int(at * SR); buf[i:i + len(a)] += a[: len(buf) - i]
put(vo, title_cue, 0.6)
for i, c in enumerate(cues): put(vo, c, starts[i + 1] + 0.35)
put(vo, close_cue, starts[-1] + 0.6)
tt = np.arange(N) / SR
def note(f, t0, dur, vol, tone="sine"):
    m = (tt >= t0) & (tt < t0 + dur); x = tt[m] - t0
    env = np.minimum(1, x / 0.4) * np.exp(-x / (dur * 0.7)); w = np.sin(2 * np.pi * f * x) + 0.3 * np.sin(4 * np.pi * f * x)
    return m, (vol * env * w).astype("float32")
mus = np.zeros(N, "float32"); chords = [[220, 261.6, 329.6], [174.6, 220, 261.6], [130.8, 164.8, 196], [196, 246.9, 293.7]]
bar = 3.2
for b in range(int(TOTAL / bar) + 2):
    ch = chords[b % 4]
    for f in ch: m, w = note(f, b * bar, bar * 1.1, 0.05); mus[m] += w[: m.sum()]
    m, w = note(ch[0] / 2, b * bar, 0.5, 0.12); mus[m] += w[: m.sum()]
    for k in range(8): m, w = note(ch[k % 3] * 2, b * bar + k * bar / 8, 0.5, 0.025); mus[m] += w[: m.sum()]
echo = np.zeros_like(mus); d = int(0.375 * SR); echo[d:] = mus[:-d] * 0.35; mus = mus + echo
def whoosh(at, dur=0.7):
    n = int(dur * SR); x = rng.standard_normal(n).astype("float32"); k = np.hanning(n)
    return (np.convolve(x, np.ones(40) / 40, "same") * k * 0.25).astype("float32")
sfx = np.zeros(N, "float32")
for at in [starts[1] - 0.5, starts[-1] - 0.5]: put(sfx, whoosh(at), at)
ch_t = np.arange(int(1.2 * SR)) / SR; chime = (np.sin(2 * np.pi * 880 * ch_t) + 0.5 * np.sin(2 * np.pi * 1320 * ch_t)) * np.exp(-ch_t * 3) * 0.12
put(sfx, chime.astype("float32"), starts[-1] + 0.1)
env = np.convolve(np.abs(vo), np.ones(int(0.05 * SR)) / int(0.05 * SR), "same"); env = np.convolve(env, np.ones(int(0.2 * SR)) / int(0.2 * SR), "same")
duck = 1 - 0.55 * np.clip(env * 7, 0, 1)
mix = vo * 1.0 + mus * duck * 0.9 + sfx
mix = np.tanh(mix * 1.3)
n_end = int(TOTAL * SR); mix = mix[:n_end]; mix *= 0.89 / max(1e-6, np.abs(mix).max())
fo = int(1.2 * SR); mix[-fo:] *= np.linspace(1, 0, fo)
sf.write(f"{W}/mix.wav", mix.astype("float32"), SR)
sh(FF, "-y", "-i", f"{W}/video_only.mp4", "-i", f"{W}/mix.wav", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT)
print("total", round(TOTAL, 1), "s ->", OUT)
