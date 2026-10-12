"""Generate a self-contained interactive flight replay (HTML) from mission_data.json."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "mission_data.json")))

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  .wrap { width: 700px; color: var(--foreground, #131A21); }
  .title { font-size: 15px; font-weight: 700; margin: 0 0 2px 0; }
  .sub { font-size: 11.5px; color: var(--muted-foreground, #5A6672); margin-bottom: 10px; }
  .row { display: flex; gap: 14px; }
  .track { position: relative; width: 62px; height: 210px; border: 1px solid var(--border, #C6CDD4);
           border-radius: 8px; overflow: hidden; flex: 0 0 auto; background: var(--card, #FDFDFC); }
  .track .fill { position: absolute; left: 0; right: 0; top: 0;
                 background: linear-gradient(180deg, #0F6E6B11, #0F6E6B22); }
  .track .can { position: absolute; left: 50%; width: 20px; height: 30px; margin-left: -10px;
                border: 2px solid #C4541F; border-radius: 5px;
                background: var(--card, #FDFDFC); }
  .track .can.chute::after { content: ""; position: absolute; left: 50%; top: -13px;
                width: 26px; height: 11px; margin-left: -13px; border-radius: 13px 13px 3px 3px;
                background: #C4541F44; border: 1.5px solid #C4541F; }
  .readout { flex: 1 1 auto; display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px;
             align-content: start; }
  .kv { border-bottom: 1px solid var(--border, #C6CDD4); padding: 3px 0; }
  .k { font-size: 10.5px; color: var(--muted-foreground, #5A6672); letter-spacing: .02em;
       text-transform: uppercase; }
  .v { font-size: 17px; font-weight: 600; font-family: ui-monospace, Menlo, monospace; }
  canvas { display: block; margin-top: 10px; border: 1px solid var(--border, #C6CDD4);
           border-radius: 8px; background: var(--card, #FDFDFC); }
  .bar { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
  button, .pill { font: inherit; font-size: 12px; padding: 5px 12px; border-radius: 999px;
           border: 1px solid var(--border, #C6CDD4); background: transparent;
           color: var(--foreground, #131A21); cursor: pointer; }
  button:hover { background: var(--accent, #E3E8EC); }
  input[type=range] { flex: 1 1 auto; accent-color: #0F6E6B; }
  .stat { font-size: 11px; color: var(--muted-foreground, #5A6672); margin-top: 8px; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10.5px;
           border: 1px solid var(--border, #C6CDD4); margin-right: 5px; }
</style></head>
<body>
<div class="wrap">
  <div class="title">CanSat Bahrain 2026 &mdash; live flight replay</div>
  <div class="sub">Decoded from __PKTS__ telemetry packets &middot; __SEC__ s of flight &middot;
    __LINK__% link success through 12% loss + CRC rejects</div>

  <div class="row">
    <div class="track" id="track">
      <div class="fill" id="fill"></div>
      <div class="can" id="can"></div>
    </div>
    <div class="readout">
      <div class="kv"><div class="k">Mission time</div><div class="v"><span id="r_t">0.0</span> s</div></div>
      <div class="kv"><div class="k">Altitude (baro)</div><div class="v"><span id="r_alt">0</span> m</div></div>
      <div class="kv"><div class="k">Descent rate</div><div class="v"><span id="r_des">0.0</span> m/s</div></div>
      <div class="kv"><div class="k">Temperature</div><div class="v"><span id="r_temp">0</span> &deg;C</div></div>
      <div class="kv"><div class="k">Humidity</div><div class="v"><span id="r_hum">0</span> %</div></div>
      <div class="kv"><div class="k">Phase</div><div class="v" id="r_phase"
        style="color:#ffb703">free fall</div></div>
    </div>
  </div>

  <canvas id="chart" width="700" height="150"></canvas>

  <div class="bar">
    <button id="play">&#9654; Play</button>
    <input type="range" id="scrub" min="0" max="1000" value="0">
    <span class="pill" id="clock">0.0 s</span>
  </div>
  <div class="stat">
    <span class="badge" id="deploy">deploy at __DEPLOY__ s</span>
    <span class="badge">terminal __TERM__ m/s</span>
    <span class="badge">chute __CHUTE__ m</span>
    <span class="badge">CRC rejected __CRC__</span>
  </div>
  <div class="bar">
    <button data-hermes-send="Re-run the CanSat mission simulation with a 60 m tower release instead of 250 m, and tell me how the flight time, descent rate and data volume change.">
      Re-run from a 60 m tower</button>
    <button data-hermes-send="Re-run the CanSat mission simulation with a 0.30 m parachute and compare the descent rate to the 5 m/s design requirement.">
      Try a 0.30 m parachute</button>
  </div>
</div>
<script>
const DATA = __DATA__;
const S = DATA.series, SUM = DATA.summary;
const t = S.t, alt = S.alt, temp = S.temp, hum = S.hum, des = S.descent;
const n = t.length, TEND = t[n-1], ALTMAX = Math.max(...alt);
const DEPLOY_IDX = (() => { for (let i=1;i<n;i++) if (des[i] > -1.3*Math.abs(SUM.mean_terminal_descent_mps)
   && Math.min(...des.slice(0,i)) < -2*Math.abs(SUM.mean_terminal_descent_mps)) return i; return 0; })();

const cv = document.getElementById('chart'), cx = cv.getContext('2d');
const track = document.getElementById('track'), fill = document.getElementById('fill');
const can = document.getElementById('can');
const SPEED = 1.6;                 // playback speed multiplier
let idx = 0, playing = false, last = 0, cursor = 0;   // cursor = mission seconds

function css(v, fb){ const g = getComputedStyle(document.body).getPropertyValue(v).trim();
  return g || fb; }
const C = { grid: 'rgba(19,26,33,.12)', text: css('--muted-foreground','#5A6672'),
            acc:'#0F6E6B', amber:'#C4541F', fg: css('--foreground','#131A21'),
            blue:'#1F5C9E' };

function y(v, min, max, h, pad){ return pad + (max - v)/(max-min) * (h - 2*pad); }

function draw(){
  const W = cv.width, H = cv.height, pad = 14;
  cx.clearRect(0,0,W,H);
  cx.strokeStyle = C.grid; cx.lineWidth = 1;
  for (let g=0; g<=4; g++){ const y = pad + g*(H-2*pad)/4;
    cx.beginPath(); cx.moveTo(pad,y); cx.lineTo(W-pad,y); cx.stroke(); }
  // descent rate trace
  const dmin = Math.min(...des), dmax = 0;
  cx.strokeStyle = C.amber; cx.lineWidth = 1.6; cx.beginPath();
  for (let i=0;i<n;i++){ const x = pad + (t[i]/TEND)*(W-2*pad);
    const py = y(des[i], dmin, dmax, H, pad); i?cx.lineTo(x,py):cx.moveTo(x,py); }
  cx.stroke();
  // temperature trace (right-hand scale, in its own lane)
  const tmin = Math.min(...temp), tmax = Math.max(...temp);
  cx.strokeStyle = C.blue; cx.lineWidth = 1.4; cx.beginPath();
  for (let i=0;i<n;i++){ const x = pad + (t[i]/TEND)*(W-2*pad);
    const py = y(temp[i], tmin, tmax, H*0.55, pad); i?cx.lineTo(x,py):cx.moveTo(x,py); }
  cx.stroke();
  // deploy marker
  const dx = pad + (t[DEPLOY_IDX]/TEND)*(W-2*pad);
  cx.strokeStyle = C.acc; cx.setLineDash([3,3]); cx.beginPath();
  cx.moveTo(dx,0); cx.lineTo(dx,H); cx.stroke(); cx.setLineDash([]);
  cx.fillStyle = C.acc; cx.font = '10px system-ui';
  cx.fillText('deploy', dx+4, 11);
  cx.fillStyle = C.amber; cx.fillText('descent rate [m/s]', pad+3, H-3);
  cx.fillStyle = C.blue; cx.fillText('temperature [C]', pad+120, H-3);
  // cursor
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
  document.getElementById('play').textContent = playing ? '\\u23F8 Pause' : '\\u25B6 Play';
  if (playing){
    if (idx >= n-1){ idx = 0; cursor = 0; render(); }   // replay from the start
    last = performance.now(); requestAnimationFrame(step);
  } };
document.getElementById('scrub').oninput = e => { playing = false;
  document.getElementById('play').textContent = '\\u25B6 Play';
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
    document.getElementById('play').textContent = '\\u25B6 Replay'; }
  else requestAnimationFrame(step);
}
render();
</script>
</body></html>"""

subs = {
    "__DATA__": json.dumps(data),
    "__PKTS__": str(data["summary"]["packets_decoded"]),
    "__SEC__": str(data["summary"]["flight_time_s"]),
    "__LINK__": str(data["summary"]["link_success_rate_pct"]),
    "__DEPLOY__": str(data["summary"]["deploy_time_s"]),
    "__TERM__": str(data["summary"]["mean_terminal_descent_mps"]),
    "__CHUTE__": str(data["summary"]["chute_diameter_m"]),
    "__CRC__": str(data["summary"]["crc_errors_rejected"]),
}
for k, v in subs.items():
    HTML = HTML.replace(k, v)

out = os.path.join(HERE, "flight_replay.html")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(HTML)
print("wrote", out, os.path.getsize(out), "bytes")

# also emit the JS on its own so test_replay_render.js can exercise it
import re as _re
js = _re.search(r"<script>(.*)</script>", HTML, _re.S).group(1)
jsout = os.path.join(HERE, "flight_replay_script.js")
with open(jsout, "w", encoding="utf-8") as fh:
    fh.write(js)
print("wrote", jsout, os.path.getsize(jsout), "bytes")
