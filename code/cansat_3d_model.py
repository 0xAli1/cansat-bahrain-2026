"""
CanSat Bahrain 2026 - printable 3D model + the dimensions the web viewer uses.

Emits ASCII STL for a fit-check print of the CanSat envelope:
    models/cansat_shell.stl   hollow cup: Ø66 x 115 mm, 1.2 mm wall, closed base, open top
    models/cansat_lid.stl     top cap: Ø66, 2 mm thick, Ø4 centred hole for the antenna

These numbers are the same ones the 3D page (site/model.html) builds its scene from:
CAN_R 33, CAN_H 115, WALL 1.2, canopy Ø580 mm (from the 5 m/s parachute sizing). Change them
in one place and change them in the other.

Two independent checks run before it declares success:
  * closed: every edge must be shared by exactly two triangles
  * oriented and correctly sized: the signed volume must be positive (outward normals) and
    match the analytic volume of the shape to within 1%

    python cansat_3d_model.py
"""
import math
import os
import sys

CAN_R = 33.0        # outer radius (Ø66)
CAN_H = 115.0       # overall height
WALL = 1.2          # shell wall
FLOOR = 1.2         # base thickness
SEG = 96            # facets around the circumference
LID_T = 2.0         # lid thickness
ANT_HOLE_R = 2.0    # Ø4 antenna hole

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "models"))


class Solid:
    """Collects triangles, writes a valid ASCII STL, and checks its own geometry."""

    def __init__(self, name):
        self.name = name
        self.tris = []

    def tri(self, a, b, c):
        self.tris.append((a, b, c))

    def quad(self, a, b, c, d):
        """Two triangles wound a-b-c-d."""
        self.tri(a, b, c)
        self.tri(a, c, d)

    @staticmethod
    def _normal(a, b, c):
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        return (0.0, 0.0, 0.0) if ln == 0 else (nx / ln, ny / ln, nz / ln)

    def write(self, path):
        with open(path, "w", encoding="ascii", newline="\n") as fh:
            fh.write("solid %s\n" % self.name)
            for a, b, c in self.tris:
                n = self._normal(a, b, c)
                fh.write("  facet normal %.6e %.6e %.6e\n    outer loop\n" % n)
                for v in (a, b, c):
                    fh.write("      vertex %.6e %.6e %.6e\n" % v)
                fh.write("    endloop\n  endfacet\n")
            fh.write("endsolid %s\n" % self.name)
        return path

    def closed(self):
        edges = {}
        for a, b, c in self.tris:
            for p, q in ((a, b), (b, c), (c, a)):
                key = (p, q) if p <= q else (q, p)
                edges[key] = edges.get(key, 0) + 1
        return {k: v for k, v in edges.items() if v != 2}

    def volume(self):
        """Signed volume in mm^3 - positive only if the normals face outward."""
        total = 0.0
        for a, b, c in self.tris:
            total += (a[0] * (b[1] * c[2] - b[2] * c[1])
                      - a[1] * (b[0] * c[2] - b[2] * c[0])
                      + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        return total


def ring(radius, y, i, segments=SEG):
    """Point i around the circumference. Index wraps, so the seam shares vertices exactly."""
    a = 2.0 * math.pi * (i % segments) / segments
    return (radius * math.cos(a), y, radius * math.sin(a))


def wall(solid, radius, y0, y1, outward=True, segments=SEG):
    """A cylindrical surface between two heights, wound so the normal faces out or in."""
    for i in range(segments):
        j = (i + 1) % segments
        a, b = ring(radius, y0, i, segments), ring(radius, y0, j, segments)
        c, d = ring(radius, y1, j, segments), ring(radius, y1, i, segments)
        if outward:
            solid.quad(d, c, b, a)
        else:
            solid.quad(a, b, c, d)


def annulus(solid, r_out, r_in, y, up=True, segments=SEG):
    for i in range(segments):
        j = (i + 1) % segments
        o0, o1 = ring(r_out, y, i, segments), ring(r_out, y, j, segments)
        i0, i1 = ring(r_in, y, i, segments), ring(r_in, y, j, segments)
        solid.quad(i0, i1, o1, o0) if up else solid.quad(o0, o1, i1, i0)


def disc(solid, radius, y, up=True, segments=SEG):
    c = (0.0, y, 0.0)
    for i in range(segments):
        p0, p1 = ring(radius, y, i, segments), ring(radius, y, (i + 1) % segments, segments)
        solid.tri(c, p1, p0) if up else solid.tri(c, p0, p1)


def build_shell():
    """Hollow cup: outer wall over the full height, inner wall from the floor up."""
    s = Solid("cansat_shell_66x115")
    r_in = CAN_R - WALL
    disc(s, CAN_R, 0.0, up=False)              # underside of the base
    wall(s, CAN_R, 0.0, CAN_H, outward=True)   # outside surface, floor to rim
    disc(s, r_in, FLOOR, up=True)              # inside floor
    wall(s, r_in, FLOOR, CAN_H, outward=False)  # internal bore
    annulus(s, CAN_R, r_in, CAN_H, up=True)    # top rim
    return s, math.pi * (CAN_R ** 2 - r_in ** 2) * CAN_H + math.pi * r_in ** 2 * FLOOR


def build_lid():
    """Flat cap with a centred antenna hole."""
    s = Solid("cansat_lid")
    wall(s, CAN_R, 0.0, LID_T, outward=True)
    wall(s, ANT_HOLE_R, 0.0, LID_T, outward=False)
    annulus(s, CAN_R, ANT_HOLE_R, LID_T, up=True)
    annulus(s, CAN_R, ANT_HOLE_R, 0.0, up=False)
    return s, math.pi * (CAN_R ** 2 - ANT_HOLE_R ** 2) * LID_T


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("writing printable models to %s" % OUT)
    print("  envelope: Ø%.1f x %.1f mm, %.1f mm wall, %d facets/rev"
          % (CAN_R * 2, CAN_H, WALL, SEG))

    ok = True
    for name, (solid, expected) in (("cansat_shell.stl", build_shell()),
                                    ("cansat_lid.stl", build_lid())):
        path = solid.write(os.path.join(OUT, name))
        bad = solid.closed()
        vol = solid.volume()
        err = abs(vol - expected) / expected * 100.0
        status = "OK" if (not bad and vol > 0 and err < 1.0) else "FAILED"
        print("  %-20s %4d facets %7.1f kB  vol %8.2f mm³ (expected %8.2f, %+.2f%%)  %s"
              % (name, len(solid.tris), os.path.getsize(path) / 1024.0, vol, expected, err, status))
        if bad:
            ok = False
            print("      not closed: %d bad edges, e.g. %s" % (len(bad), list(bad)[:2]))
        if vol <= 0:
            ok = False
            print("      normals are inverted (signed volume is negative)")
        if err >= 1.0:
            ok = False
            print("      volume is wrong - geometry does not match the intended shape")

    # dimensional assertions on the emitted triangles
    shell, _ = build_shell()
    ys = [v[1] for t in shell.tris for v in t]
    rs = [math.hypot(v[0], v[2]) for t in shell.tris for v in t]
    print("\n  shell spans y %.2f … %.2f mm, max radius %.2f mm (Ø%.1f)"
          % (min(ys), max(ys), max(rs), max(rs) * 2))
    assert abs(min(ys)) < 1e-9 and abs(max(ys) - CAN_H) < 1e-9, "shell height wrong"
    assert abs(max(rs) - CAN_R) < 1e-9, "shell radius wrong"
    assert abs(max(rs) - CAN_R) < 1e-9 and min(rs) < 1e-9, "base is not a closed disc"

    print("\n%s" % ("PASS: both parts closed, correctly oriented and dimensionally right"
                    if ok else "FAILED"))
    sys.exit(0 if ok else 1)
