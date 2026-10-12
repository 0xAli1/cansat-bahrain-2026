"""
Render the 3D page in headless Chrome (software WebGL) and screenshot each view.

Needed because the 3D model has to be *looked at* to be judged: this drives the page over the
DevTools protocol, waits for the scene to report itself ready, exercises the interaction hooks
(modelView / modelSelect / modelIsolate / modelMove), and captures a PNG of each state.

Usage:
    python shot3d.py <dir> <page> <width> <height> [label=js] [label=js] ...

Example:
    python shot3d.py ../repo model.html 1400 900 \
        assembled= default= \
        exploded="window.modelView('exploded')" \
        deployed="window.modelView('deployed')" \
        picked="window.modelSelect('battery')"
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

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    "/usr/bin/google-chrome", "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

# software WebGL in headless: without these the context creation fails and the
# page falls back to its poster image
GPU_FLAGS = [
    "--enable-unsafe-swiftshader",
    "--use-angle=swiftshader",
    "--use-gl=angle",
    "--ignore-gpu-blocklist",
    "--enable-webgl",
    "--disable-gpu-sandbox",
]


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    return None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


class Chrome:
    def __init__(self, browser, width, height, scale=1):
        self.prof = tempfile.mkdtemp(prefix="shot3d-")
        self.port = free_port()
        self.proc = subprocess.Popen(
            [browser, "--headless=new", "--no-first-run", "--no-default-browser-check",
             "--hide-scrollbars", "--mute-audio", "--remote-allow-origins=*",
             *GPU_FLAGS,
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
            self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120)
            self.id = 0
            self.send("Page.enable")
            self.send("Runtime.enable")
            self.send("Log.enable")
            self.send("Runtime.consoleAPICalled")
            self.send("Emulation.setDeviceMetricsOverride", width=width, height=height,
                      deviceScaleFactor=scale, mobile=False)
        except Exception:
            self.close()
            raise

    def send(self, method, **params):
        self.id += 1
        mid = self.id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg.get("result", {})

    def drain(self):
        """Collect console errors emitted since the last drain (non-blocking)."""
        out = []
        self.ws.settimeout(0.25)
        try:
            while True:
                msg = json.loads(self.ws.recv())
                if msg.get("method") == "Runtime.exceptionThrown":
                    d = msg["params"]["exceptionDetails"]
                    out.append("EXCEPTION " + str(d.get("text"))
                               + " " + str(d.get("exception", {}).get("description", ""))[:200])
                elif msg.get("method") == "Runtime.consoleAPICalled":
                    if msg["params"]["type"] in ("error", "warning"):
                        args = " ".join(str(a.get("value", a.get("description", "")))
                                        for a in msg["params"]["args"])
                        out.append(msg["params"]["type"].upper() + " " + args[:200])
        except Exception:
            pass
        self.ws.settimeout(120)
        return out

    def goto(self, url):
        self.send("Page.navigate", url=url)

    def evaluate(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True)
        return r.get("result", {}).get("value")

    def wait_ready(self, timeout=45):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.evaluate("window.__MODEL_READY__ === true"):
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def shot(self, path, selector="#stage"):
        """Clip to the 3D view itself - the viewport screenshot cuts the canvas off."""
        rect = None
        if selector:
            rect = json.loads(self.evaluate(
                "(() => { const el = document.querySelector(%r); if (!el) return '{\"found\":false}';"
                " const r = el.getBoundingClientRect();"
                " return JSON.stringify({found:true, x:r.left, y:r.top,"
                " width:r.width, height:r.height}); })()" % selector))
        params = {"format": "png", "captureBeyondViewport": True}
        if rect and rect.get("found") and rect["width"] > 10:
            params["clip"] = {"x": rect["x"], "y": rect["y"],
                              "width": rect["width"], "height": rect["height"], "scale": 1}
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
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(getattr(self, "prof", ""), ignore_errors=True)


def main():
    base, page, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    steps = []
    for a in sys.argv[5:]:
        if "=" in a:
            label, js = a.split("=", 1)
        else:
            label, js = a, ""
        steps.append((label, js))
    if not steps:
        steps = [("default", "")]

    browser = find_browser()
    if not browser:
        print("no chrome")
        sys.exit(1)

    url = "file:///" + os.path.join(os.path.abspath(base), page).replace(os.sep, "/")
    shots = os.path.join(os.path.abspath(base), "shots")
    os.makedirs(shots, exist_ok=True)

    c = Chrome(browser, w, h)
    try:
        c.goto(url)
        ready = c.wait_ready()
        print("model ready:", ready)
        for e in c.drain():
            print("  ", e)
        if not ready:
            print("scene never became ready - dumping status")
            print("  ", c.evaluate("({err: window.__MODEL_ERR__ || null, "
                                   "hasThree: !!window.modelStatus})"))
        for i, (label, js) in enumerate(steps):
            if js:
                c.evaluate(js)
            time.sleep(1.4)                     # let the tween settle
            status = c.evaluate("window.modelStatus ? JSON.stringify(window.modelStatus()) : '{}'")
            path = os.path.join(shots, f"{os.path.splitext(page)[0]}-{label}.png")
            c.shot(path)
            errs = c.drain()
            print(f"  [{label}] {status}")
            for e in errs:
                print("      ", e)
            print(f"        {path}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
