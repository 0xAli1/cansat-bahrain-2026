"""
Generate the interactive flight replay from mission_data.json.

Emits four artifacts from one template:
  flight_replay.html        self-contained widget for the Hermes chat pane
                            (theme-variable aware, includes the chat re-run buttons)
  flight_replay_site.html   the same widget for the public site: responsive, no
                            chat-only buttons
  flight_replay_page.html   standalone site page wrapping the widget
  flight_replay_script.js   the JS extracted, so test_replay_render.js can run it

The canvas is sized from its layout box x devicePixelRatio and redrawn on resize,
so it is correct at 320 px and on a 4K desktop alike.

Run:  python gen_replay.py     (after cansat_mission_demo.py has produced the data)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "mission_data.json")))

# ---------------------------------------------------------------- shared template
CSS = """
  .wrap { width: 100%; max-width: 700px; color: var(--foreground, #131A21); }
  .title { font-family: var(--display, "Bahnschrift", "Arial Narrow", sans-serif);
           font-size: 15px; font-weight: 600; margin: 0 0 2px 0; }
  .sub { font-size: 11.5px; color: var(--muted-foreground, #5A6672); margin-bottom: 10px; }
  .row { display: flex; gap: 12px; align-items: flex-start; }
  .track { position: relative; width: 54px; height: 200px; flex: 0 0 auto;
           border: 1px solid var(--border, #C6CDD4); border-radius: 8px;
           overflow: hidden; background: var(--card, #FDFDFC); }
  .track .fill { position: absolute; left: 0; right: 0; top: 0;
                 background: linear-gradient(180deg, #0F6E6B11, #0F6E6B22); }
  .track .can { position: absolute; left: 50%; width: 20px; height: 30px; margin-left: -10px;
                border: 2px solid #C4541F; border-radius: 5px;
                background: var(--card, #FDFDFC); }
  .track .can.chute::after { content: ""; position: absolute; left: 50%; top: -13px;
                width: 26px; height: 11px; margin-left: -13px;
                border-radius: 13px 13px 3px 3px;
                background: #C4541F44; border: 1.5px solid #C4541F; }
  .readout { flex: 1 1 auto; min-width: 0; display: grid;
             grid-template-columns: 1fr 1fr; gap: 5px 12px; align-content: start; }
  .kv { border-bottom: 1px solid var(--border, #C6CDD4); padding: 3px 0; min-width: 0; }
  .k { font-size: 10.5px; color: var(--muted-foreground, #5A6672); letter-spacing: .02em;
       text-transform: uppercase; }
  .v { font-size: 17px; font-weight: 600; font-family: ui-monospace, Menlo, monospace;
       font-variant-numeric: tabular-nums; }
  canvas { display: block; width: 100%; height: 150px; margin-top: 10px;
           border: 1px solid var(--border, #C6CDD4); border-radius: 8px;
           background: var(--card, #FDFDFC); }
  .bar { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
  button, .pill { font: inherit; font-size: 12px; padding: 5px 12px; border-radius: 999px;
           border: 1px solid var(--border, #C6CDD4); background: transparent;
           color: var(--foreground, #131A21); cursor: pointer; white-space: nowrap; }
  button:hover { background: var(--accent, #E3E8EC); }
  input[type=range] { flex: 1 1 140px; min-width: 0; accent-color: #0F6E6B; }
  .stat { font-size: 11px; color: var(--muted-foreground, #5A6672); margin-top: 8px; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10.5px;
           border: 1px solid var(--border, #C6CDD4); margin: 0 5px 4px 0; }
  .hint { font-size: 11.5px; color: var(--muted-foreground, #5A6672); margin: 10px 0 0;
          max-width: 62ch; }
  .hint code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11px;
               word-break: break-all; }
  @media (max-width: 560px) {
    .track { width: 42px; height: 140px; }
    .track .can { height: 24px; }
    canvas { height: 118px; }
    .v { font-size: 15px; }
    .k { font-size: 9.5px; }
    .readout { gap: 3px 10px; }
    .sub { margin-bottom: 8px; }
  }
"""

MARKUP = """
<div class="wrap">
  <div class="title">__SITETITLE__Live flight replay</div>
  <div class="sub">Decoded from __PKTS__ telemetry packets &middot; __SEC__ s of flight &middot;
    __LINK__% link success through 12% loss + CRC rejects</div>

  <div class="row">
    <div class="track" id="track">
      <div class="fill" id="fill"></div>
      <div class="can" id="can"></div>
    </div>
    <div class="readout">
      <div class="kv"><div class="k">Mission time</div><div class="v"><span id="r_t">0.0</span> s</div></div>
      <div class="kv"><div class="k">Altitude</div><div class="v"><span id="r_alt">0</span> m</div></div>
      <div class="kv"><div class="k">Descent rate</div><div class="v"><span id="r_des">0.0</span> m/s</div></div>
      <div class="kv"><div class="k">Temperature</div><div class="v"><span id="r_temp">0</span> &deg;C</div></div>
      <div class="kv"><div class="k">Humidity</div><div class="v"><span id="r_hum">0</span> %</div></div>
      <div class="kv"><div class="k">Phase</div><div class="v" id="r_phase"
        style="color:#C4541F">free fall</div></div>
    </div>
  </div>

  <canvas id="chart"></canvas>

  <div class="bar">
    <button id="play">&#9654; Play</button>
    <input type="range" id="scrub" min="0" max="1000" value="0" aria-label="Flight position">
    <span class="pill" id="clock">0.0 s</span>
  </div>
  <div class="stat">
    <span class="badge">deploy __DEPLOY__ s</span>
    <span class="badge">terminal __TERM__ m/s</span>
    <span class="badge">chute __CHUTE__ m</span>
    <span class="badge">CRC rejected __CRC__</span>
  </div>
__EXTRA__
</div>
"""

CHAT_EXTRA = """  <div class="bar">
    <button data-hermes-send="Re-run the CanSat mission simulation with a 60 m tower release instead of 250 m, and tell me how the flight time, descent rate and data volume change.">
      Re-run from a 60 m tower</button>
    <button data-hermes-send="Re-run the CanSat mission simulation with a 0.30 m parachute and compare the descent rate to the 5 m/s design requirement.">
      Try a 0.30 m parachute</button>
  </div>"""

SITE_EXTRA = """  <p class="hint">Change the release altitude, the deployment timer or the canopy size in
  <code>code/cansat_mission_demo.py</code> and re-run it &mdash; the telemetry, the figures and
  this replay are all rebuilt from that single run.</p>"""

JS = r"""
const DATA = __DATA__;
const S = DATA.series, SUM = DATA.summary;
const t = S.t, alt = S.alt, temp = S.temp, hum = S.hum, des = S.descent;
const n = t.length, TEND = t[n-1], ALTMAX = Math.max(...alt);
const TERM = Math.abs(SUM.mean_terminal_descent_mps);
const DEPLOY_IDX = (() => {
  let lowest = Infinity;
  for (let i=0;i<n;i++){
    if (des[i] < lowest) lowest = des[i];
    if (des[i] > -1.3*TERM && lowest < -2*TERM) return i;
  }
  return 0;
})();

const cv = document.getElementById('chart'), cx = cv.getContext('2d');
const track = document.getElementById('track'), fill = document.getElementById('fill');
const can = document.getElementById('can');
const SPEED = 1.6;                     // playback speed multiplier
let idx = 0, playing = false, last = 0, cursor = 0, W = 700, H = 150;

function css(v, fb){ const g = getComputedStyle(document.body).getPropertyValue(v).trim();
  return g || fb; }
const C = { grid: 'rgba(19,26,33,.12)', text: css('--muted-foreground','#5A6672'),
            acc:'#0F6E6B', amber:'#C4541F', fg: css('--foreground','#131A21'),
            blue:'#1F5C9E' };

// size the backing store from the layout box, so the chart is sharp and correct
// at any viewport width (320 px phone through 4K desktop)
function sizeCanvas(){
  const dpr = window.devicePixelRatio || 1;
  const box = cv.getBoundingClientRect();
  W = Math.max(240, Math.round(box.width));
  H = Math.max(80, Math.round(box.height));
  cv.width = Math.round(W * dpr);
  cv.height = Math.round(H * dpr);
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function y(v, min, max, h, pad){ return pad + (max - v)/(max-min) * (h - 2*pad); }

function draw(){
  const pad = 20;
  cx.clearRect(0, 0, W, H);
  cx.strokeStyle = C.grid; cx.lineWidth = 1;
  for (let g=0; g<=4; g++){ const gy = pad + g*(H-2*pad)/4;
    cx.beginPath(); cx.moveTo(pad,gy); cx.lineTo(W-pad,gy); cx.stroke(); }

  const dmin = Math.min(...des), dmax = 0;

  // axis values, so the chart reads quantitatively and not just as a trend
  cx.fillStyle = C.text; cx.font = '10px system-ui';
  cx.fillText('0', 2, pad + 9);
  cx.fillText(String(Math.round(dmin)), 2, H - pad + 4);

  cx.strokeStyle = C.amber; cx.lineWidth = 1.6; cx.beginPath();
  for (let i=0;i<n;i++){ const x = pad + (t[i]/TEND)*(W-2*pad);
    const py = y(des[i], dmin, dmax, H, pad); i?cx.lineTo(x,py):cx.moveTo(x,py); }
  cx.stroke();

  const tmin = Math.min(...temp), tmax = Math.max(...temp);
  cx.strokeStyle = C.blue; cx.lineWidth = 1.4; cx.beginPath();
  for (let i=0;i<n;i++){ const x = pad + (t[i]/TEND)*(W-2*pad);
    const py = y(temp[i], tmin, tmax, H*0.55, pad); i?cx.lineTo(x,py):cx.moveTo(x,py); }
  cx.stroke();

  const dx = pad + (t[DEPLOY_IDX]/TEND)*(W-2*pad);
  cx.strokeStyle = C.acc; cx.setLineDash([3,3]); cx.beginPath();
  cx.moveTo(dx,0); cx.lineTo(dx,H); cx.stroke(); cx.setLineDash([]);
  cx.fillStyle = C.acc; cx.font = '11px system-ui';
  cx.fillText('deploy ' + t[DEPLOY_IDX].toFixed(1) + ' s', Math.min(dx+5, W-84), 12);
  cx.fillStyle = C.amber;
  cx.fillText('descent rate m/s', pad+2, H-3);
  cx.fillStyle = C.blue;
  cx.fillText('temperature C', Math.min(pad+108, W-92), H-3);

  const cx0 = pad + (t[idx]/TEND)*(W-2*pad);
  cx.strokeStyle = C.fg; cx.lineWidth = 1.2; cx.beginPath();
  cx.moveTo(cx0,0); cx.lineTo(cx0,H); cx.stroke();
}

function render(){
  const k = idx;
  document.getElementById('r_t').textContent = t[k].toFixed(1);
  document.getElementById('r_alt').textContent = alt[k].toFixed(0);
  document.getElementById('r_des').textContent = des[k].toFixed(1);
  document.getElementById('r_temp').textContent = temp[k].toFixed(1);
  document.getElementById('r_hum').textContent = hum[k].toFixed(0);
  document.getElementById('clock').textContent = t[k].toFixed(1) + ' s';
  const phase = document.getElementById('r_phase');
  if (k >= DEPLOY_IDX){ phase.textContent = 'under canopy'; phase.style.color = C.acc; }
  else { phase.textContent = 'free fall'; phase.style.color = C.amber; }
  const frac = alt[k]/ALTMAX;
  can.style.top = (6 + (1-frac)*(track.clientHeight-42)) + 'px';
  can.classList.toggle('chute', k >= DEPLOY_IDX);
  fill.style.height = (frac*100) + '%';
  document.getElementById('scrub').value = Math.round(1000*t[k]/TEND);
  draw();
}

document.getElementById('play').onclick = () => { playing = !playing;
  document.getElementById('play').textContent = playing ? '\u23F8 Pause' : '\u25B6 Play';
  if (playing){
    if (idx >= n-1){ idx = 0; cursor = 0; render(); }   // replay from the start
    last = performance.now(); requestAnimationFrame(step);
  } };
document.getElementById('scrub').oninput = e => { playing = false;
  document.getElementById('play').textContent = '\u25B6 Play';
  const target = (e.target.value/1000)*TEND;
  idx = t.findIndex(v => v >= target); if (idx < 0) idx = n-1;
  cursor = t[idx]; render(); };

function step(now){
  if (!playing) return;
  const dtSeconds = (now-last)/1000; last = now;
  cursor += dtSeconds*SPEED;                 // mission time advances with real time
  while (idx < n-1 && t[idx+1] <= cursor) idx++;
  render();
  if (idx >= n-1){ playing = false;
    document.getElementById('play').textContent = '\u25B6 Replay'; }
  else requestAnimationFrame(step);
}

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { sizeCanvas(); render(); }, 120);
});

sizeCanvas();
render();
"""

SUBS = {
    "__PKTS__": str(data["summary"]["packets_decoded"]),
    "__SEC__": str(data["summary"]["flight_time_s"]),
    "__LINK__": str(data["summary"]["link_success_rate_pct"]),
    "__DEPLOY__": str(data["summary"]["deploy_time_s"]),
    "__TERM__": str(data["summary"]["mean_terminal_descent_mps"]),
    "__CHUTE__": str(data["summary"]["chute_diameter_m"]),
    "__CRC__": str(data["summary"]["crc_errors_rejected"]),
}


def build(extra, site_title=False):
    html = MARKUP.replace("__EXTRA__", extra)
    html = html.replace("__SITETITLE__", "Simulated mission &mdash; " if site_title else "")
    for k, v in SUBS.items():
        html = html.replace(k, v)
    return html.strip()


CARD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flight replay &mdash; CanSat Bahrain 2026</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#EDEFF2;color:#131A21;
    font-family:system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    display:flex;justify-content:center;padding:22px 16px 34px}
  .card{background:#FDFDFC;border:1px solid #C6CDD4;padding:18px 20px;
    width:100%;max-width:760px;box-sizing:border-box}
  .card h1{font-family:"Bahnschrift","DIN Alternate","Roboto Condensed","Arial Narrow",sans-serif;
    font-weight:600;font-size:1.05rem;margin:0 0 4px}
  .card p.intro{font-size:.84rem;color:#5A6672;margin:0 0 16px;max-width:66ch}
__CSS__
</style></head><body>
<div class="card">
  <h1>Flight replay &mdash; simulated mission</h1>
  <p class="intro">Reconstructed from the __PKTS__ decoded telemetry packets. Play it, or drag
  the slider to scrub. Not a real flight: the descent comes from a physics model, then the
  readings were packed into the same 34-byte frames the firmware transmits and decoded back by
  the ground station.</p>
__MARKUP__
</div>
<script>
__JS__
</script>
</body></html>
"""

if __name__ == "__main__":
    chat_markup = build(CHAT_EXTRA)
    site_markup = build(SITE_EXTRA, site_title=True)
    js = JS.replace("__DATA__", json.dumps(data))

    # 1. chat widget: self-contained, theme-variable aware, with the chat buttons
    chat = ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
            f"<style>{CSS}</style></head>\n<body>\n{chat_markup}\n<script>\n{js}\n"
            "</script>\n</body></html>")
    p1 = os.path.join(HERE, "flight_replay.html")
    open(p1, "w", encoding="utf-8", newline="\n").write(chat)

    # 2. site fragment: style + markup + script, for inlining into the landing page
    frag = f"<style>{CSS}</style>\n{site_markup}\n<script>\n{js}\n</script>"
    p2 = os.path.join(HERE, "flight_replay_site.html")
    open(p2, "w", encoding="utf-8", newline="\n").write(frag)

    # 3. standalone site page
    page = (CARD.replace("__CSS__", CSS).replace("__MARKUP__", site_markup)
                .replace("__JS__", js).replace("__PKTS__", SUBS["__PKTS__"]))
    p3 = os.path.join(HERE, "flight_replay_page.html")
    open(p3, "w", encoding="utf-8", newline="\n").write(page)

    # 4. the JS on its own, for test_replay_render.js
    p4 = os.path.join(HERE, "flight_replay_script.js")
    open(p4, "w", encoding="utf-8", newline="\n").write(js)

    for p in (p1, p2, p3, p4):
        print(f"wrote {os.path.basename(p):28s} {os.path.getsize(p):>7,} bytes")
