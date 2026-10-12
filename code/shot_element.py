"""
Screenshot a single element, at a given viewport width.

  python shot_element.py <dir> <page> <css-selector> <width>

Reuses the Chrome driver from mobile_check.py. Full-page screenshots of a long
mobile page are capped in height, so the element you care about can be missing;
this clips straight to it.
"""
import json
import os
import sys

from mobile_check import Chrome, find_browser

base, page, selector, width = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
path = os.path.join(os.path.abspath(base), page)
url = "file:///" + path.replace(os.sep, "/")

c = Chrome(find_browser(), width, 900)
try:
    c.goto(url)
    rect = json.loads(c.evaluate(
        "(() => { const el = document.querySelector(%r);"
        " if (!el) return JSON.stringify({found:false});"
        " const r = el.getBoundingClientRect();"
        " return JSON.stringify({found:true, x:r.left+window.scrollX, y:r.top+window.scrollY,"
        " width:r.width, height:r.height}); })()" % selector))
    if not rect.get("found"):
        print("selector not found:", selector)
        sys.exit(1)
    print(f"{selector} -> {rect['width']:.0f}x{rect['height']:.0f} at y={rect['y']:.0f}")
    pad = 6
    out = c.send("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                 clip={"x": max(0, rect["x"] - pad), "y": max(0, rect["y"] - pad),
                       "width": min(rect["width"] + 2 * pad, width),
                       "height": rect["height"] + 2 * pad, "scale": 2})
    import base64
    dest = os.path.join(os.path.abspath(base), "shots",
                        f"{os.path.splitext(page)[0]}-{selector.strip('.#')}-{width}.png")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(base64.b64decode(out["data"]))
    print("shot:", dest, os.path.getsize(dest), "bytes")
finally:
    c.close()
