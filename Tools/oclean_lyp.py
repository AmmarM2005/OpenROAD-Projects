#!/usr/bin/env python3
"""oclean_lyp.py <platform.lyp> <out.lyp> : copy a KLayout layer-properties file with label, pin, net,
boundary, cut, resistor, probe, short and model layers hidden, so a layout opens readable."""
import re, sys
import xml.etree.ElementTree as ET

HIDE = re.compile(r"\.(label|pin|net|res|cut|bound\w*|probe|short|model|hv|text|dnwell|blockage|option\d|waffleDrop)\b|prBoundary|areaid|\btext\b|label|\bpin\b|blockage|waffleDrop", re.I)

def main(src, dst):
    tree = ET.parse(src)
    hidden = total = 0
    for props in tree.getroot().iter("properties"):
        name = (props.findtext("name") or props.findtext("source") or "")
        vis = props.find("visible")
        if vis is None or not name:
            continue
        total += 1
        if HIDE.search(name):
            vis.text = "false"
            hidden += 1
    tree.write(dst, encoding="utf-8", xml_declaration=True)
    print(f"{hidden} of {total} layers hidden")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: oclean_lyp.py <in.lyp> <out.lyp>")
    main(sys.argv[1], sys.argv[2])
