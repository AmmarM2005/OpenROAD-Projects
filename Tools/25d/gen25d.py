#!/usr/bin/env python3
"""gen25d.py: build a KLayout 2.5d (D25) script from a platform's tech LEF and layer map."""
import argparse, datetime, json, os, re, subprocess, sys, tempfile
from pathlib import Path
from xml.sax.saxutils import escape

LYD25 = """<?xml version="1.0" encoding="utf-8"?>
<klayout-macro>
 <description>2.5D view (auto-generated)</description>
 <version/>
 <category>d25</category>
 <prolog/>
 <epilog/>
 <doc/>
 <autorun>false</autorun>
 <autorun-early>false</autorun-early>
 <shortcut/>
 <show-in-menu>false</show-in-menu>
 <group-name/>
 <menu-path/>
 <interpreter>dsl</interpreter>
 <dsl-interpreter-name>d25-dsl-xml</dsl-interpreter-name>
 <text>@TEXT@</text>
</klayout-macro>
"""

def parse_lef(text):
    layers, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        if cur is None:
            m = re.match(r"LAYER\s+(\S+)\s*$", s)
            if m:
                cur = {"name": m.group(1), "type": None, "thickness": None}
            continue
        m = re.match(r"TYPE\s+(\w+)", s)
        if m:
            cur["type"] = m.group(1).upper(); continue
        m = re.match(r"THICKNESS\s+([0-9.eE+-]+)", s)
        if m:
            cur["thickness"] = float(m.group(1)); continue
        m = re.match(r"END\s+(\S+)", s)
        if m and m.group(1) == cur["name"]:
            layers.append(cur); cur = None
    return layers

def find_tech(flow, plat):
    pdir = flow / "platforms" / plat
    lefdir = pdir / "lef" if (pdir / "lef").is_dir() else pdir
    files = sorted(lefdir.glob("*.tlef")) + sorted(f for f in lefdir.glob("*.lef") if "tech" in f.name.lower())
    files += [f for f in sorted(lefdir.glob("*.lef")) if f not in files]
    for f in files:
        try:
            layers = parse_lef(f.read_text(errors="ignore"))
        except OSError:
            continue
        if any(l["type"] == "ROUTING" and l["thickness"] for l in layers):
            return f, layers
    return None, []

def layer_map(flow, plat):
    pdir = flow / "platforms" / plat
    m = {}
    for lyt in sorted(pdir.glob("*.lyt")):
        t = lyt.read_text(errors="ignore")
        for name, l, d in re.findall(r"'([^':]+?)\s*:\s*(\d+)/(\d+)'", t):
            n = name.strip()
            if n.endswith(".drawing"):
                n = n[:-8]
            if "." in n:
                continue
            m.setdefault(n, (int(l), int(d)))
    for lyp in sorted(pdir.glob("*.lyp")):
        t = lyp.read_text(errors="ignore")
        for name, l, d in re.findall(r"<name>([A-Za-z0-9_]+)\.drawing\s*-\s*(\d+)/(\d+)</name>", t):
            m.setdefault(name, (int(l), int(d)))
    return m

def gds_layers(klayout, gds):
    rb = tempfile.NamedTemporaryFile("w", suffix=".rb", delete=False)
    rb.write('ly = RBA::Layout.new\nly.read(ENV["GDS25D"])\n'
             'ly.layer_infos.each { |li| puts "LAYER #{li.layer} #{li.datatype}" }\n')
    rb.close()
    try:
        r = subprocess.run([klayout, "-b", "-r", rb.name], env={**os.environ, "GDS25D": str(gds)},
                           capture_output=True, text=True, timeout=180)
        found = {(int(a), int(b)) for a, b in re.findall(r"LAYER (\d+) (\d+)", r.stdout)}
        return found or None
    except Exception:
        return None
    finally:
        os.unlink(rb.name)

def build(layers, lmap, used, fe):
    rows, skipped, z = [], [], 0.0
    has = lambda key: key is not None and (used is None or key in used)
    for name, L, D, h in fe:
        if has((L, D)):
            rows.append((name, (L, D), z, z + h, h, "front-end (illustrative)"))
            z += h
    seq = [l for l in layers if l["type"] in ("ROUTING", "CUT")]
    first = next((i for i, l in enumerate(seq) if l["type"] == "ROUTING"), None)
    if first is None:
        return rows, skipped, None
    seq = seq[first:]
    keys = [lmap.get(l["name"]) for l in seq]
    last = max((i for i, l in enumerate(seq) if l["type"] == "ROUTING" and has(keys[i])), default=len(seq) - 1)
    seq, keys = seq[:last + 1], keys[:last + 1]
    for i, (l, key) in enumerate(zip(seq, keys)):
        if l["type"] == "ROUTING":
            t = l["thickness"] or 0.30
            src = "tech LEF" if l["thickness"] else "assumed"
        elif l["thickness"]:
            t, src = l["thickness"], "tech LEF"
        else:
            lo = seq[i - 1]["thickness"] or 0.30
            hi = (seq[i + 1]["thickness"] if i + 1 < len(seq) else None) or lo
            t, src = max(0.10, round(0.6 * min(lo, hi), 3)), "gap (illustrative)"
        if key is None:
            skipped.append(l["name"])
        elif has(key):
            rows.append((l["name"], key, z, z + t, t, src))
        z += t
    top = next((l["name"] for l in reversed(seq) if l["type"] == "ROUTING"), None)
    return rows, skipped, top

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True)
    ap.add_argument("--flow", required=True)
    ap.add_argument("--gds", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--klayout", default="klayout")
    ap.add_argument("--fallback", default="")
    a = ap.parse_args()
    flow, out = Path(a.flow), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    lef, layers = find_tech(flow, a.platform)
    lmap = layer_map(flow, a.platform)
    used = gds_layers(a.klayout, a.gds)
    fe_file = Path(__file__).parent / "frontend.json"
    fe = json.loads(fe_file.read_text()).get(a.platform, []) if fe_file.exists() else []

    rows, skipped, top = ([], [], None)
    if layers:
        rows, skipped, top = build(layers, lmap, used, fe)

    stamp = datetime.date.today().isoformat()
    if rows:
        lines = ["# 2.5D stack for %s, generated %s" % (a.platform, stamp),
                 "# metal thickness: %s ; cut (via) heights are illustrative gaps" % lef.name]
        for name, (L, D), z0, z1, t, src in rows:
            lines.append('z(input(%d, %d), zstart: %.3f, zstop: %.3f, name: "%s")' % (L, D, z0, z1, name))
        text = "\n".join(lines) + "\n"
        print("  %-9s %-8s %7s %7s %7s  %s" % ("layer", "GDS", "z0", "z1", "thick", "source"))
        for name, (L, D), z0, z1, t, src in rows:
            print("  %-9s %-8s %7.3f %7.3f %7.3f  %s" % (name, "%d/%d" % (L, D), z0, z1, t, src))
        print("  highest metal in this GDS: %s" % top)
        if skipped:
            print("  no GDS layer number found for: " + ", ".join(skipped))
        if used is None:
            print("  (could not read the GDS layer list, all layers of the stack are included)")
    elif a.fallback and Path(a.fallback).exists():
        text = Path(a.fallback).read_text()
        print("  no thickness data found for %s, using the static script %s" % (a.platform, Path(a.fallback).name))
    else:
        print("  ERROR: no thickness data for platform %s and no fallback script" % a.platform)
        sys.exit(1)

    (out / "view25d.rb").write_text(text)
    (out / "view25d.lyd25").write_text(LYD25.replace("@TEXT@", escape(text)))
    print("  wrote %s/view25d.lyd25 (and view25d.rb)" % out)

if __name__ == "__main__":
    main()
