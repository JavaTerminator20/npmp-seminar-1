"""
Analiza rezultatov: tabele in grafi (faza 5).

Vhodne datoteke (vsaka skripta piše v svojo podmapo results/<skripta>/):
  transpile_run/structural.csv - strukturne metrike, obvezno
  simulate/ideal.csv           - kontrola na idealnem simulatorju
  simulate/noisy.csv           - P_pravilno na šumnem simulatorju
  hardware/hardware.csv        - P_pravilno na pravem procesorju
  hardware/ibm_jobs.csv        - seznam nalog na procesorju
Če katere od zadnjih štirih datotek ni (npr. pred zagonom na procesorju), ustrezni del analize preskočimo.

Izhodne datoteke:
  results/analyze/tabela1_strukturne.csv (+ .md)  strukturne metrike po ravneh
  results/analyze/tabela2_pravilnost.csv (+ .md)  P_pravilno po ravneh in platformah
  results/analyze/tabela3_hipoteze.csv   (+ .md)  preverjanje obeh hipotez
  figures/graf1_dvokubitna_vrata.pdf       dvokubitna vrata po ravneh
  figures/graf2_pravilnost.pdf             P_pravilno: šumni model in procesor
  figures/graf3_vrata_proti_P_v3.pdf       dvokubitna vrata proti P_pravilno (nelinearni osi)
  figures/graf4_serija_A_B.pdf             serija A proti seriji B

Datoteke .md so iste tabele za pregled (predogled v VS Code, GitHub), urejene kot tabele v poročilu:
seriji A in B drug ob drugi, ena decimalka, P v %, pri spremembah pozitivno = izboljšanje.

Grafi in tabele nastanejo SAMO iz datotek v results/, zato jih lahko kadarkoli ponovno narišemo brez novih simulacij.

Zagon:
    python src/analyze.py
"""

import argparse
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # risanje v datoteko, brez okna
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullFormatter, NullLocator
import numpy as np
import pandas as pd

RESULTS = Path(__file__).resolve().parent.parent / "results"
FIGURES = Path(__file__).resolve().parent.parent / "figures"
# Podmape results/ po skriptah (enako kot v transpile_run.py)
SUB_TRANSPILE = "transpile_run"
SUB_SIMULATE = "simulate"
SUB_HARDWARE = "hardware"
SUB_ANALYZE = "analyze"

LEVELS = [0, 1, 2, 3]

# Vrstni red vezij (od najmanjšega do največjega) in imena za grafe
CIRCUIT_LABELS = {
    "toffoli": "Toffoli",
    "fredkin": "Fredkin",
    "polni_sestevalnik": "Polni seštevalnik",
    "cuccaro": "Cuccaro",
}
CIRCUITS = list(CIRCUIT_LABELS)

PLATFORM_LABELS = {
    "idealno": "idealni simulator",
    "sumni_model": "šumni model",
    "sumni_model_isto_seme": "šumni model (seme kot na procesorju)",
    "procesor": "procesor",
}

# Meje iz hipotez (prijava teme)
H1_GATES_PCT = 30    # H1: z ravni 0 na 1 vsaj 30 % manj dvokubitnih vrat
H2_GATES_PCT = 10    # H2: med ravnema 2 in 3 manj kot 10 % razlike v vratih
H2_P_PT = 3          # H2: in manj kot 3 odstotne točke razlike v P_pravilno

# Barve: kategorične barve v stalnem vrstnem redu (vezje ima vedno isto barvo in obliko točke),
# ravni pa odtenki ene barve od svetle (raven 0) do temne (raven 3), ker so ravni urejene.
CIRCUIT_COLORS = {
    "toffoli": "#2a78d6",
    "fredkin": "#eb6834",
    "polni_sestevalnik": "#1baf7a",
    "cuccaro": "#eda100",
}
CIRCUIT_MARKERS = {
    "toffoli": "o",
    "fredkin": "s",
    "polni_sestevalnik": "^",
    "cuccaro": "D",
}
LEVEL_COLORS = ["#b7d3f2", "#74a9e8", "#2a78d6", "#174a8c"]
COLOR_PRED = "#a3a29c"          # siva za vezje pred prevajanjem
COLOR_NOISY = "#2a78d6"         # šumni model
COLOR_HW = "#eb6834"            # procesor
COLOR_A = "#2a78d6"             # serija A
COLOR_B = "#1baf7a"             # serija B

plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#8a8984",
    "axes.labelcolor": "#2b2a28",
    "xtick.color": "#52514e",
    "ytick.color": "#52514e",
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": "#e4e3df",
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,        # mreža za stolpci
    "legend.frameon": False,
    "pdf.fonttype": 42,            # pisave vdelane v PDF kot besedilo
})


# ---------------------------------------------------------------------
# Branje podatkov
# ---------------------------------------------------------------------

def read_optional(path):
    """Prebere CSV, če obstaja, sicer vrne None."""
    if not path.exists():
        print(f"  (ni datoteke {path.name}, ta del preskočim)")
        return None
    # vhod in izhod sta niza bitov: brez dtype=str bi pandas "001" prebral kot število 1
    return pd.read_csv(path, dtype={"vhod": str, "pricakovano": str, "job_id": str})


def load_hardware(res):
    """
    Prebere hardware.csv in obdrži samo glavna zagona (nalogi A in B).
    Poskusni zagon (8 vhodov Toffolija) bi sicer pokvaril povprečja.
    """
    hw = read_optional(res / "hardware.csv")
    if hw is None:
        return None
    jobs_path = res / "ibm_jobs.csv"
    if jobs_path.exists():
        jobs = pd.read_csv(jobs_path, dtype=str)
        keep = jobs.loc[jobs["naloga"].isin(["A", "B"]), "job_id"]
        hw = hw[hw["job_id"].isin(keep)]
        for naloga, group in jobs[jobs["job_id"].isin(keep)].groupby("naloga"):
            if len(group) > 1:
                print(f"  POZOR: naloga {naloga} ima {len(group)} zagonov, povprečim čez vse.")
    return hw if not hw.empty else None


def sort_circuits(df, col="vezje"):
    """Uredi vrstice po vrstnem redu vezij v CIRCUITS."""
    df = df.copy()
    df[col] = pd.Categorical(df[col], categories=CIRCUITS, ordered=True)
    return df.sort_values([col] + [c for c in ["serija", "platforma", "raven"] if c in df.columns])


# ---------------------------------------------------------------------
# Tabela 1: strukturne metrike
# ---------------------------------------------------------------------

def table_structural(st):
    """
    Povprečje in standardni odklon strukturnih metrik čez semena za vsako (vezje, serija, raven).
    Vrstice "pred" ostanejo, kot so.
    """
    pred = st[st["raven"] == "pred"].copy()
    rest = st[st["raven"] != "pred"].copy()
    rest["raven"] = rest["raven"].astype(int)

    agg = rest.groupby(["vezje", "serija", "raven"]).agg(
        st_kubitov=("st_kubitov", "mean"),
        dvokubitna_povp=("st_dvokubitnih", "mean"),
        dvokubitna_std=("st_dvokubitnih", "std"),
        dvokubitna_min=("st_dvokubitnih", "min"),
        dvokubitna_max=("st_dvokubitnih", "max"),
        globina_povp=("globina", "mean"),
        globina_std=("globina", "std"),
        st_vrat_povp=("st_vrat", "mean"),
        cas_s_povp=("cas_s", "mean"),
        st_semen=("seme", "count"),
    ).reset_index()

    pred_rows = pd.DataFrame({
        "vezje": pred["vezje"],
        "serija": "-",
        "raven": "pred",
        "st_kubitov": pred["st_kubitov"],
        "dvokubitna_povp": pred["st_dvokubitnih"],
        "dvokubitna_std": 0.0,
        "dvokubitna_min": pred["st_dvokubitnih"],
        "dvokubitna_max": pred["st_dvokubitnih"],
        "globina_povp": pred["globina"],
        "globina_std": 0.0,
        "st_vrat_povp": pred["st_vrat"],
        "cas_s_povp": None,
        "st_semen": 0,
    })
    table = pd.concat([pred_rows, agg], ignore_index=True)
    table["raven"] = table["raven"].astype(str)
    return sort_circuits(table)


def dec1(x):
    """
    Zaokroži na eno decimalko, polovice navzgor (1,65 -> 1,7; 15,25 -> 15,3), kot v poročilu.
    Sam f"{x:.1f}" bi 1.6499999 (napaka zapisa 1,65) in 15,25 zaokrožil na 1,6 in 15,2.
    """
    return Decimal(str(round(float(x), 9))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def md_table(rows, n_text=1):
    """Seznam vrstic (slovarji z enakimi ključi) -> tabela Markdown. Prvih n_text stolpcev je poravnanih levo."""
    head = list(rows[0])
    align = [":--"] * n_text + ["--:"] * (len(head) - n_text)
    lines = [head, align] + [[str(r[h]) for h in head] for r in rows]
    return "\n".join("| " + " | ".join(line) + " |" for line in lines) + "\n"


def md_structural(table):
    """
    Markdown: vrstice = vezja in povprečje čez vezja, stolpci = pred ter ravni 0-3 v seriji A in B.
    Vrednosti so povprečja čez semena (prva tabela je enaka tabeli g10:tab:vrata v poročilu).
    """
    cols = pd.MultiIndex.from_tuples([("-", "pred")] + [(s, str(l)) for s in "AB" for l in LEVELS])
    heads = ["pred"] + [f"{s}{l}" for s in "AB" for l in LEVELS]
    t = table.assign(vezje=table["vezje"].astype(str))
    labels = {**CIRCUIT_LABELS, "povprecje": "povprečje"}
    out = ["# Tabela 1: strukturne metrike", "",
           "Povprečje čez 10 semen. A0 = serija A, raven 0. Vrstica povprečje je povprečje čez vezja.", ""]
    for metric, title, scale in [("dvokubitna_povp", "Dvokubitna vrata", 1), ("globina_povp", "Globina", 1),
                                 ("st_vrat_povp", "Vsa vrata", 1), ("cas_s_povp", "Čas prevajanja [ms]", 1000)]:
        w = t.pivot(index="vezje", columns=["serija", "raven"], values=metric).reindex(index=CIRCUITS, columns=cols)
        w = w.astype(float) * scale
        w.loc["povprecje"] = w.mean()
        rows = [{"Vezje": labels[v], **{h: "–" if pd.isna(x) else f"{dec1(x):.1f}" for h, x in zip(heads, w.loc[v])}}
                for v in w.index]
        out += [f"## {title}", "", md_table(rows)]
    return "\n".join(out)


# ---------------------------------------------------------------------
# Tabela 2: P_pravilno po ravneh in platformah
# ---------------------------------------------------------------------

def per_run(df):
    """
    En zagon = (platforma, vezje, serija, raven, seme). P_pravilno zagona je povprečje čez vse vhode vezja.
    """
    return (df.groupby(["platforma", "vezje", "serija", "raven", "seme"])
            .agg(P=("P", "mean"), st_dvokubitnih=("st_dvokubitnih", "mean"))
            .reset_index())


def table_correctness(ideal, noisy, hw):
    """
    Povprečni P_pravilno za (platforma, vezje, serija, raven).
    P_std je standardni odklon čez semena (pri procesorju je seme eno).
    Če imamo procesor, dodamo še šumni model samo s semeni, ki smo jih pognali na procesorju
    (enaka prevedena vezja, poštena primerjava).
    """
    frames = [df for df in (ideal, noisy, hw) if df is not None]
    runs = per_run(pd.concat(frames, ignore_index=True))

    if hw is not None and noisy is not None:
        hw_seeds = hw[["vezje", "serija", "raven", "seme"]].drop_duplicates()
        same = per_run(noisy).merge(hw_seeds, on=["vezje", "serija", "raven", "seme"])
        same["platforma"] = "sumni_model_isto_seme"
        runs = pd.concat([runs, same], ignore_index=True)

    table = (runs.groupby(["platforma", "vezje", "serija", "raven"])
             .agg(P_povp=("P", "mean"), P_std=("P", "std"), st_semen=("seme", "count"))
             .reset_index())
    return sort_circuits(table), runs


def md_correctness(table):
    """Markdown: P_pravilno v %, vrstice = vezje x platforma, stolpci = ravni 0-3 v seriji A in B."""
    order = [p for p in PLATFORM_LABELS if p in set(table["platforma"])]
    P = table.assign(vezje=table["vezje"].astype(str)).set_index(["vezje", "platforma", "serija", "raven"])["P_povp"]
    rows = []
    for name in CIRCUITS:
        for plat in order:
            row = {"Vezje": CIRCUIT_LABELS[name], "Platforma": PLATFORM_LABELS[plat]}
            for s in "AB":
                for l in LEVELS:
                    k = (name, plat, s, l)
                    row[f"{s}{l}"] = f"{dec1(100 * P[k]):.1f}" if k in P.index else "–"
            rows.append(row)
    out = ["# Tabela 2: verjetnost pravilnega rezultata P_pravilno [%]", "",
           "Šumni model: povprečje čez 10 semen. Procesor: eno seme. A0 = serija A, raven 0.", "",
           md_table(rows, n_text=2)]
    if "sumni_model_isto_seme" in order:
        out += ["Opomba: »šumni model« je povprečje čez 10 semen prevajalnika (0–9). "
                "»šumni model (seme kot na procesorju)« ni povprečje, ampak samo eno seme prevajalnika, "
                "isto kot je bilo uporabljeno na pravem procesorju IBM. Šumni model je v obeh vrsticah isti.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------
# Tabela 3: preverjanje hipotez
# ---------------------------------------------------------------------

def table_hypotheses(struct_table, corr_table):
    """
    Za vsako (serija, vezje, platforma) izračuna:
      zmanjsanje_0_1_pct   = (vrata_0 - vrata_1) / vrata_0 * 100
      razlika_P_0_1_pt     = (P_1 - P_0) * 100          (odstotne točke)
      razlika_2_3_pct      = (vrata_2 - vrata_3) / vrata_2 * 100
      razlika_P_2_3_pt     = (P_3 - P_2) * 100
    H1 (vrata): zmanjšanje 0 -> 1 je večje od 30 %.
    H2: |razlika vrat 2 -> 3| < 10 % in |razlika P 2 -> 3| < 3 točke.
    Število vrat je iz structural.csv (povprečje čez semena), P_pravilno iz platforme.
    """
    gates = struct_table[struct_table["raven"] != "pred"].copy()
    gates["raven"] = gates["raven"].astype(int)
    gates = gates.set_index(["serija", "vezje", "raven"])["dvokubitna_povp"]
    P = corr_table.set_index(["platforma", "serija", "vezje", "raven"])["P_povp"]

    rows = []
    platforms = [p for p in ["sumni_model", "sumni_model_isto_seme", "procesor"] if p in set(corr_table["platforma"])]
    for serija in ["A", "B"]:
        for plat in platforms:
            for name in CIRCUITS:
                try:
                    g = [gates[(serija, name, l)] for l in LEVELS]
                    p = [P[(plat, serija, name, l)] for l in LEVELS]
                except KeyError:
                    continue      # te kombinacije ni (npr. B na procesorju)
                rows.append({
                    "serija": serija,
                    "platforma": plat,
                    "vezje": name,
                    "vrata_0": g[0],
                    "vrata_1": g[1],
                    "zmanjsanje_0_1_pct": (g[0] - g[1]) / g[0] * 100,
                    "P_0": p[0],
                    "P_1": p[1],
                    "razlika_P_0_1_pt": (p[1] - p[0]) * 100,
                    "vrata_2": g[2],
                    "vrata_3": g[3],
                    "razlika_2_3_pct": (g[2] - g[3]) / g[2] * 100,
                    "P_2": p[2],
                    "P_3": p[3],
                    "razlika_P_2_3_pt": (p[3] - p[2]) * 100,
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # povprečje čez vezja za vsako (serija, platforma)
    num = [c for c in df.columns if c not in ("serija", "platforma", "vezje")]
    avg = df.groupby(["serija", "platforma"])[num].mean().reset_index()
    avg["vezje"] = "povprecje"
    # Kot v Metodah: najprej povprečimo števila vrat in P čez vezja, nato izračunamo spremembo.
    # (Povprečje odstotkov bi dalo drugačen rezultat; pri P je oboje enako, pri vratih ne.)
    avg["zmanjsanje_0_1_pct"] = (avg["vrata_0"] - avg["vrata_1"]) / avg["vrata_0"] * 100
    avg["razlika_2_3_pct"] = (avg["vrata_2"] - avg["vrata_3"]) / avg["vrata_2"] * 100
    avg["razlika_P_0_1_pt"] = (avg["P_1"] - avg["P_0"]) * 100
    avg["razlika_P_2_3_pt"] = (avg["P_3"] - avg["P_2"]) * 100
    df = pd.concat([df, avg], ignore_index=True)

    df["H1_vrata"] = df["zmanjsanje_0_1_pct"] > H1_GATES_PCT
    df["H2"] = (df["razlika_2_3_pct"].abs() < H2_GATES_PCT) & (df["razlika_P_2_3_pt"].abs() < H2_P_PT)

    # vrstni red: serija, platforma, vezja, povprečje na koncu
    df["_p"] = df["platforma"].map({p: i for i, p in enumerate(PLATFORM_LABELS)})
    df["_v"] = df["vezje"].map({c: i for i, c in enumerate(CIRCUITS + ["povprecje"])})
    return df.sort_values(["serija", "_p", "_v"]).drop(columns=["_p", "_v"]).reset_index(drop=True)


def signed(x):
    """Število z obveznim predznakom, brez "-0.0" (npr. +17.7, -25.0, 0.0)."""
    s = f"{dec1(x):+.1f}"
    return "0.0" if s in ("+0.0", "-0.0") else s


def md_hypotheses(df):
    """
    Markdown: spremembe med ravnema po enačbi v Metodah, pozitivno = izboljšanje.
    Ena tabela za vsako serijo (serija A je enaka tabeli g10:tab:spremembe v poročilu) in odločitvi o hipotezah.
    """
    labels = {**CIRCUIT_LABELS, "povprecje": "povprečje"}
    short = {"sumni_model": "š", "procesor": "p"}
    out = ["# Tabela 3: preverjanje hipotez", "",
           "Δn v %, ΔP v odstotnih točkah, pozitivno = izboljšanje. "
           "š = šumni model (povprečje čez semena), p = procesor. "
           "Pri povprečju je Δn izračunan iz povprečnih števil vrat.", "",
           f"H1 vrata: Δn 0→1 nad {H1_GATES_PCT} %. "
           f"H2: |Δn 2→3| pod {H2_GATES_PCT} % in |ΔP 2→3| pod {H2_P_PT} o. t.", ""]
    for serija in ["A", "B"]:
        t = df[df["serija"] == serija].set_index(["vezje", "platforma"])
        plats = [p for p in short if p in t.index.get_level_values("platforma")]
        if not plats:
            continue
        rows = []
        for v in CIRCUITS + ["povprecje"]:
            g = t.loc[(v, plats[0])]          # število vrat je za vse platforme enako
            row = {"Vezje": labels[v], "Δn 0→1": signed(g["zmanjsanje_0_1_pct"])}
            row.update({f"ΔP {short[p]} 0→1": signed(t.loc[(v, p), "razlika_P_0_1_pt"]) for p in plats})
            row["Δn 2→3"] = signed(g["razlika_2_3_pct"])
            row.update({f"ΔP {short[p]} 2→3": signed(t.loc[(v, p), "razlika_P_2_3_pt"]) for p in plats})
            row["H1 vrata"] = "da" if g["H1_vrata"] else "ne"
            row.update({f"H2 {short[p]}": "da" if t.loc[(v, p), "H2"] else "ne" for p in plats})
            rows.append(row)
        out += [f"## Serija {serija}", "", md_table(rows)]
    return "\n".join(out)


# ---------------------------------------------------------------------
# Grafi
# ---------------------------------------------------------------------

def graf1_gates(struct_table, out, serija="A"):
    """Stolpci: število dvokubitnih vrat po ravneh, skupine po vezjih."""
    fig, ax = plt.subplots(figsize=(6.3, 2.6))
    width = 0.16
    bars = [("pred", "pred prevajanjem", COLOR_PRED)] + [(str(l), f"raven {l}", LEVEL_COLORS[l]) for l in LEVELS]
    for i, (raven, label, color) in enumerate(bars):
        xs, ys, errs = [], [], []
        for j, name in enumerate(CIRCUITS):
            t = struct_table[(struct_table["vezje"] == name) & (struct_table["raven"] == raven)
                             & (struct_table["serija"].isin([serija, "-"]))]
            if t.empty:
                continue
            xs.append(j + (i - 2) * width)
            ys.append(t["dvokubitna_povp"].iloc[0])
            errs.append(t["dvokubitna_std"].iloc[0])
        ax.bar(xs, ys, width, label=label, color=color, edgecolor="white", linewidth=0.8)
        if raven != "pred":
            ax.errorbar(xs, ys, yerr=errs, fmt="none", ecolor="#52514e", elinewidth=0.7, capsize=1.5)
    ax.set_xticks(range(len(CIRCUITS)))
    ax.set_xticklabels([CIRCUIT_LABELS[c] for c in CIRCUITS])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Število dvokubitnih vrat")
    ax.legend(ncol=5, loc="upper left", bbox_to_anchor=(0, 1.15), handlelength=1.2, columnspacing=1.2)
    fig.tight_layout()
    fig.savefig(out / "graf1_dvokubitna_vrata.pdf")
    plt.close(fig)


def graf2_correctness(corr_table, out, serija="A"):
    """P_pravilno po ravneh: šumni model in procesor drug ob drugem."""
    has_hw = "procesor" in set(corr_table["platforma"])
    fig, axes = plt.subplots(1, len(CIRCUITS), figsize=(6.3, 2.3), sharey=True)
    width = 0.38 if has_hw else 0.6
    series = [("sumni_model", "šumni model (povprečje čez semena)", COLOR_NOISY)]
    if has_hw:
        series.append(("procesor", "procesor", COLOR_HW))
    for ax, name in zip(axes, CIRCUITS):
        for i, (plat, label, color) in enumerate(series):
            t = corr_table[(corr_table["platforma"] == plat) & (corr_table["vezje"] == name) & (corr_table["serija"] == serija)]
            t = t.set_index("raven").reindex(LEVELS)
            offset = (i - (len(series) - 1) / 2) * width
            xs = [l + offset for l in LEVELS]
            ax.bar(xs, t["P_povp"], width, label=label, color=color, edgecolor="white", linewidth=0.8)
            if plat == "sumni_model":
                ax.errorbar(xs, t["P_povp"], yerr=t["P_std"], fmt="none", ecolor="#52514e", elinewidth=0.7, capsize=1.5)
        ax.set_title(CIRCUIT_LABELS[name])
        ax.set_xticks(LEVELS)
        ax.set_xlabel("raven")
        ax.tick_params(axis="x", length=0)
        ax.set_ylim(0, 1.0)
    axes[0].set_ylabel(r"$P_\mathrm{pravilno}$")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="upper left", bbox_to_anchor=(0.06, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(out / "graf2_pravilnost.pdf")
    plt.close(fig)


def graf3_scatter(runs, out):
    """
    Razsevni diagram: število dvokubitnih vrat proti P_pravilno.
    Ena točka = en zagon (P povprečen čez vhode). Barva in oblika točke = vezje,
    polna točka = šumni model, prazna = procesor.
    Na linearnih oseh so majhna vezja (malo vrat, P blizu 1) zbita v zgornjem levem kotu, zato:
      os x je logaritemska,
      os y ima skalo z = -log10(1 - P): vsak enak korak navzgor pomeni pol manjšo napako,
      zato je razdalja od 80 % do 90 % enaka kot od 90 % do 95 %.
    Pri majhni napaki vrat eps je 1 - P približno n * eps, zato točke ležijo približno na premici.
    """
    P_MAX = 0.98     # zgornja meja osi; pri 100 % bi bila skala neskončna
    # širina 4.6 palca = širina besedila v zborniku (117 mm), da pisava ni pomanjšana
    fig, ax = plt.subplots(figsize=(4.6, 2.4))
    for name in CIRCUITS:
        for plat, filled in [("sumni_model", True), ("procesor", False)]:
            t = runs[(runs["vezje"] == name) & (runs["platforma"] == plat)]
            over = t["P"] > P_MAX
            if over.any():
                print(f"  POZOR: graf3: {over.sum()} zagonov ({name}, {plat}) s P nad {P_MAX:.0%} ni narisanih.")
                t = t[~over]
            if t.empty:
                continue
            color = CIRCUIT_COLORS[name]
            ax.scatter(t["st_dvokubitnih"], t["P"], marker=CIRCUIT_MARKERS[name], s=10 if filled else 24,
                       facecolors=color if filled else "none", edgecolors="white" if filled else color,
                       linewidths=0.3 if filled else 1.0, alpha=0.6 if filled else 1.0)
    ax.grid(True, axis="both")

    ax.set_xscale("log")
    ax.set_xlim(5, 100)
    ax.xaxis.set_major_locator(FixedLocator([5, 10, 20, 50, 100]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    # skala -log10(1 - P) in njen inverz; clip, da P = 1 (izven osi) ne da deljenja z 0
    ax.set_yscale("function", functions=(lambda p: -np.log10(1 - np.clip(p, 0, 1 - 1e-9)),
                                         lambda z: 1 - 10 ** (-z)))
    ax.set_ylim(0, P_MAX)
    ax.yaxis.set_major_locator(FixedLocator([0.2, 0.5, 0.8, 0.9, 0.95, 0.98]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{100 * y:g} %"))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_xlabel("Število dvokubitnih vrat (prevedeno vezje)")
    ax.set_ylabel(r"$P_\mathrm{pravilno}$")

    handles = [Line2D([], [], linestyle="none", marker=CIRCUIT_MARKERS[c], markerfacecolor=CIRCUIT_COLORS[c], markeredgecolor="white", markersize=6, label=CIRCUIT_LABELS[c]) for c in CIRCUITS]
    handles.append(Line2D([], [], linestyle="none", marker="o", markerfacecolor="#6b6a65", markeredgecolor="white", markersize=6, label="šumni model"))
    if "procesor" in set(runs["platforma"]):
        handles.append(Line2D([], [], linestyle="none", marker="o", markerfacecolor="none", markeredgecolor="#6b6a65", markersize=6, label="procesor"))
    # spodaj levo ni točk (majhna vezja imajo velik P), zato legenda tam ne prekrije podatkov
    ax.legend(handles=handles, loc="lower left", ncol=2, fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "graf3_vrata_proti_P_v3.pdf")
    plt.close(fig)


def graf4_series(struct_table, corr_table, out):
    """
    Serija A (postavitev izbere prevajalnik) proti seriji B (vse ravni imajo isto postavitev).
    Zgoraj število dvokubitnih vrat, spodaj P_pravilno na šumnem modelu.
    """
    fig, axes = plt.subplots(2, len(CIRCUITS), figsize=(6.3, 3.6), sharex=True)
    for j, name in enumerate(CIRCUITS):
        for serija, color in [("A", COLOR_A), ("B", COLOR_B)]:
            label = f"serija {serija}"
            g = struct_table[(struct_table["vezje"] == name) & (struct_table["serija"] == serija)].copy()
            g["raven"] = g["raven"].astype(int)
            g = g.sort_values("raven")
            axes[0, j].errorbar(g["raven"], g["dvokubitna_povp"], yerr=g["dvokubitna_std"], color=color, marker="o", markersize=4, linewidth=1.5, capsize=1.5, elinewidth=0.7, label=label)
            p = corr_table[(corr_table["platforma"] == "sumni_model") & (corr_table["vezje"] == name) & (corr_table["serija"] == serija)]
            p = p.sort_values("raven")
            axes[1, j].errorbar(p["raven"], p["P_povp"], yerr=p["P_std"], color=color, marker="o", markersize=4, linewidth=1.5, capsize=1.5, elinewidth=0.7, label=label)
        axes[0, j].set_title(CIRCUIT_LABELS[name])
        axes[0, j].set_ylim(bottom=0)
        # število vrat je celo število: oznake brez decimalk
        axes[0, j].yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
        axes[1, j].set_ylim(0, 1.0)
        axes[1, j].set_xticks(LEVELS)
        axes[1, j].set_xlabel("raven")
    axes[0, 0].set_ylabel("Dvokubitna vrata")
    axes[1, 0].set_ylabel(r"$P_\mathrm{pravilno}$ (šumni model)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="upper left", bbox_to_anchor=(0.08, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out / "graf4_serija_A_B.pdf")
    plt.close(fig)


# ---------------------------------------------------------------------
# Glavni program
# ---------------------------------------------------------------------

def print_hypotheses(hyp):
    """Kratek izpis preverjanja hipotez (serija A)."""
    labels = {**CIRCUIT_LABELS, "povprecje": "POVPREČJE"}
    for plat in hyp["platforma"].unique():
        t = hyp[(hyp["serija"] == "A") & (hyp["platforma"] == plat)]
        if t.empty:
            continue
        print(f"\nHipoteze, serija A, {PLATFORM_LABELS[plat]}:")
        for _, r in t.iterrows():
            print(f"  {labels[r['vezje']]:18s} "
                  f"0->1: vrata {signed(-r['zmanjsanje_0_1_pct']):>6} %, P {signed(r['razlika_P_0_1_pt']):>6} t. "
                  f"(H1 vrata: {'da' if r['H1_vrata'] else 'ne'}) | "
                  f"2->3: vrata {signed(-r['razlika_2_3_pct']):>6} %, P {signed(r['razlika_P_2_3_pt']):>6} t. "
                  f"(H2: {'da' if r['H2'] else 'ne'})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=str(RESULTS), help="mapa results/ s podmapami skript")
    parser.add_argument("--figures-dir", default=str(FIGURES), help="mapa za grafe")
    args = parser.parse_args()
    root = Path(args.results_dir)
    res = root / SUB_ANALYZE          # sem gredo tabele
    res.mkdir(parents=True, exist_ok=True)
    fig_dir = Path(args.figures_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("Berem rezultate ...")
    st = pd.read_csv(root / SUB_TRANSPILE / "structural.csv", dtype={"raven": str})
    ideal = read_optional(root / SUB_SIMULATE / "ideal.csv")
    noisy = read_optional(root / SUB_SIMULATE / "noisy.csv")
    hw = load_hardware(root / SUB_HARDWARE)

    # --- tabela 1 in graf 1: samo strukturne metrike ---
    struct_table = table_structural(st)
    struct_table.to_csv(res / "tabela1_strukturne.csv", index=False)
    (res / "tabela1_strukturne.md").write_text(md_structural(struct_table), encoding="utf-8")
    graf1_gates(struct_table, fig_dir)
    print("Tabela 1 in graf 1: končano")

    if noisy is None:
        print("Brez noisy.csv ni tabel 2-3 in grafov 2-4. Najprej poženite src/simulate.py.")
        return

    # --- tabela 2: P_pravilno ---
    corr_table, runs = table_correctness(ideal, noisy, hw)
    corr_table.to_csv(res / "tabela2_pravilnost.csv", index=False)
    (res / "tabela2_pravilnost.md").write_text(md_correctness(corr_table), encoding="utf-8")

    # --- tabela 3: hipoteze ---
    hyp = table_hypotheses(struct_table, corr_table)
    hyp.to_csv(res / "tabela3_hipoteze.csv", index=False)
    (res / "tabela3_hipoteze.md").write_text(md_hypotheses(hyp), encoding="utf-8")
    print("Tabeli 2 in 3: končano")

    # --- grafi 2-4 ---
    graf2_correctness(corr_table, fig_dir)
    graf3_scatter(runs, fig_dir)
    graf4_series(struct_table, corr_table, fig_dir)
    print(f"Grafi zapisani v {fig_dir}")

    # --- kontrola idealnega simulatorja ---
    if ideal is not None:
        bad = ideal[ideal["P"] < 1.0]
        print(f"\nIdealni simulator: {len(ideal) - len(bad)}/{len(ideal)} vezij s P = 1.0")

    print_hypotheses(hyp)


if __name__ == "__main__":
    main()
