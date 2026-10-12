"""
Mobile layout verifier — drives headless Chrome over the DevTools protocol.

Headless Chrome on Windows clamps its window to ~500 px, so --window-size cannot
produce a real phone viewport. This uses Emulation.setDeviceMetricsOverride
instead, which gives an exact viewport, and it returns both:
  * a measurement: which elements exceed the viewport width (real overflow data)
  * a screenshot: so the rendering can be looked at, not guessed at

Run:  python mobile_check.py                 # default widths 360 / 390 / 430
      python mobile_check.py 320 390
"""
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

HERE = os.path.dirname(os.path.abspath(__file__))
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

MEASURE = """
(() => {
  const vw = document.documentElement.clientWidth;
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1 || r.width > vw + 1) {
      const id = el.tagName.toLowerCase()
        + (el.id ? '#' + el.id : '')
        + (typeof el.className === 'string' && el.className
           ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
      out.push(id + ' w=' + Math.round(r.width) + ' right=' + Math.round(r.right));
    }
  }
  return JSON.stringify({
    vw: vw,
    docScrollWidth: document.documentElement.scrollWidth,
    overflow: document.documentElement.scrollWidth > vw + 1,
    offenders: out.slice(0, 14),
    offenderCount: out.length
  });
})()
"""


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    return None


def wait_port(port, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


class Chrome:
    def __init__(self, browser, width, height, scale=2):
        self.prof = tempfile.mkdtemp(prefix="cdp-prof-")
        self.port = free_port()
        self.proc = subprocess.Popen(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", "--hide-scrollbars", "--mute-audio",
             "--remote-allow-origins=*",
             f"--remote-debugging-port={self.port}",
             f"--user-data-dir={self.prof}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        try:
            if not wait_port(self.port):
                raise RuntimeError("devtools port never opened")
            targets = json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/list"))
            page = [t for t in targets if t["type"] == "page"][0]
            self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=90)
            self.id = 0
            self.send("Page.enable")
            self.send("Runtime.enable")
            self.send("Emulation.setDeviceMetricsOverride", width=width, height=height,
                      deviceScaleFactor=scale, mobile=True)
        except Exception:
            self.close()                       # never leak a headless chrome
            raise

    def send(self, method, **params):
        self.id += 1
        mid = self.id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg.get("result", {})

    def goto(self, url, settle=1.6):
        self.send("Page.navigate", url=url)
        time.sleep(settle)

    def evaluate(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True)
        return r.get("result", {}).get("value")

    def screenshot(self, path, full_page=True):
        params = {"format": "png", "captureBeyondViewport": full_page}
        if full_page:
            metrics = self.send("Page.getLayoutMetrics")
            cs = metrics.get("cssContentSize") or metrics.get("contentSize")
            if cs:
                params["clip"] = {"x": 0, "y": 0, "width": cs["width"],
                                  "height": min(cs["height"], 6000), "scale": 1}
        r = self.send("Page.captureScreenshot", **params)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(r["data"]))
        return path

    def close(self):
        if getattr(self, "ws", None):
            try:
                self.ws.close()
            except Exception:
                pass
        proc = getattr(self, "proc", None)
        if proc:
            # /T kills the whole tree: headless chrome spawns renderer children
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(getattr(self, "prof", ""), ignore_errors=True)


def check(browser, page, width, height=844, shot_dir=None, base=None):
    base = base or HERE
    if base.startswith("http"):
        url = base.rstrip("/") + "/" + page          # measure the deployed site
    else:
        url = "file:///" + os.path.join(base, page).replace(os.sep, "/")
    c = Chrome(browser, width, height)
    try:
        c.goto(url, settle=2.4 if base.startswith("http") else 1.6)
        raw = c.evaluate(MEASURE)
        data = json.loads(raw)
        shot = None
        if shot_dir:
            shot = c.screenshot(os.path.join(shot_dir, f"{os.path.splitext(page)[0]}-{width}.png"))
        return data, shot
    finally:
        c.close()


if __name__ == "__main__":
    browser = find_browser()
    if not browser:
        print("no Chrome/Edge found")
        sys.exit(1)

    # usage: python mobile_check.py [dir|url] [widths...]   (defaults to this script's dir)
    args = sys.argv[1:]
    base = HERE
    for a in list(args):
        if a.startswith("http"):
            base = a
            args.remove(a)
        elif os.path.isdir(a):
            base = os.path.abspath(a)
            args.remove(a)
    widths = [int(a) for a in args] or [360, 390, 430]

    shots = os.path.join(HERE if base.startswith("http") else base, "shots")
    os.makedirs(shots, exist_ok=True)
    print("browser:", browser)
    print("checking:", base)
    bad = 0
    if base.startswith("http"):
        pages = ["index.html", "plan.html", "replay.html", "model.html"]
    else:
        pages = [f for f in sorted(os.listdir(base))
                 if f.endswith(".html") and not f.startswith("_")]
    for page in pages:
        if not base.startswith("http") and not os.path.exists(os.path.join(base, page)):
            continue
        for w in widths:
            data, shot = check(browser, page, w, shot_dir=shots, base=base)
            flag = "X" if data["overflow"] else "."
            bad += 1 if data["overflow"] else 0
            print(f"  [{flag}] {page:13s} @{w:>4}px  vw={data['vw']} "
                  f"scrollWidth={data['docScrollWidth']} offenders={data['offenderCount']}")
            for o in data["offenders"]:
                print(f"          {o}")
            if shot:
                print(f"          shot: {shot}")
    print("\nOVERFLOW PAGES:", bad)
