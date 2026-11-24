"""
Bouwt de twee rekenverslagen:
    docs/rekenverslag_A_coolprop.pdf  – CoolProp met Cengel-check
    docs/rekenverslag_B_cengel.pdf    – alleen Cengel-handberekening

Gebruik (vanuit de repo-root):
    pip install CoolProp numpy matplotlib jinja2
    python docs/rekenverslag/genereer.py          # beide versies (pdflatex/latexmk nodig)
    python docs/rekenverslag/genereer.py --tex    # alleen .tex en figuren, niet compileren
"""
import math
import os
import shutil
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "..", ".."))

import jinja2  # noqa: E402

import figuren  # noqa: E402
import waarden  # noqa: E402

BUILD = os.path.join(HIER, "build")
UIT = os.path.join(HIER, "..")


def n(x, d=1, plus=False):
    """Getal met decimale komma en dunne spatie als duizendtalscheiding (LaTeX)."""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "--"
    if isinstance(x, bool):
        return "ja" if x else "nee"
    s = f"{abs(x):,.{d}f}"
    geheel, _, dec = s.partition(".")
    if len(geheel.replace(",", "")) <= 4:
        geheel = geheel.replace(",", "")
    geheel = geheel.replace(",", "\\,")
    s = geheel + ("{,}" + dec if dec else "")
    if x < 0 and float(f"{abs(x):.{d}f}") != 0:
        s = "\\ensuremath{-}" + s
    elif plus:
        s = "+" + s
    return s


def g(x, sig=4):
    """Getal met vast aantal significante cijfers."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "--"
    if x == 0:
        return "0"
    d = max(0, sig - 1 - int(math.floor(math.log10(abs(x)))))
    return n(x, d)


def pct(x, d=1):
    return n(x * 100, d) + "\\,\\%"


def tex(s):
    if s is None:
        return ""
    s = str(s)
    for a, b in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"), ("#", "\\#"), ("_", "\\_"),
                 ("<", "\\textless{}"), (">", "\\textgreater{}")):
        s = s.replace(a, b)
    return s


def omgeving():
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.join(HIER, "templates")),
        block_start_string="\\BLOCK{", block_end_string="}",
        variable_start_string="\\VAR{", variable_end_string="}",
        comment_start_string="\\#{", comment_end_string="}",
        line_statement_prefix="%%", line_comment_prefix="%#",
        trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True, autoescape=False, undefined=jinja2.StrictUndefined,
    )
    env.globals.update(n=n, g=g, pct=pct, tex=tex, abs=abs, max=max, min=min, round=round, len=len,
                       enumerate=enumerate, sorted=sorted, zip=zip)
    env.filters["tex"] = tex
    return env


def bouw(versie, compileren=True):
    i = waarden.invoer()
    RA_, RB_ = waarden.versie_A(), waarden.versie_B()
    R = RA_ if versie == "A" else RB_
    A_ = RA_
    map_ = os.path.join(BUILD, versie)
    os.makedirs(map_, exist_ok=True)
    figuren.alles(R, i, os.path.join(map_, "fig"))
    ctx = dict(R=R, I=i, A=versie == "A", B=versie == "B", wp1=R["wp1"], wp2=R["wp2"],
               WA=waarden.wat_als(versie), KM=waarden.koudemiddelen(A_), RA=A_, RB=RB_, T0=273.15, PATM=101.325,
               C=waarden.CENGEL, A4=waarden.TAB_A4)
    tekst = omgeving().get_template("main.tex").render(**ctx)
    naam = "rekenverslag_A_coolprop" if versie == "A" else "rekenverslag_B_cengel"
    pad = os.path.join(map_, naam + ".tex")
    with open(pad, "w", encoding="utf-8") as fh:
        fh.write(tekst)
    if compileren:
        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", naam + ".tex"]
        res = subprocess.run(cmd, cwd=map_, capture_output=True, text=True, errors="replace")
        if res.returncode != 0:
            print(res.stdout[-4000:])
            raise SystemExit(f"LaTeX-fout in versie {versie}")
        shutil.copy(os.path.join(map_, naam + ".pdf"), os.path.join(UIT, naam + ".pdf"))
        print("geschreven:", os.path.normpath(os.path.join(UIT, naam + ".pdf")))
    return pad


if __name__ == "__main__":
    comp = "--tex" not in sys.argv
    versies = [v for v in ("A", "B") if v in sys.argv[1:]] or ["A", "B"]
    for v in versies:
        bouw(v, comp)
