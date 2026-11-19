"""
Zagon na pravem kvantnem procesorju IBM (faza 4).

Naloge (prvi argument):
  poskus   - Toffoli, 8 vhodov, raven 1, 1000 ponovitev.
             Po zagonu v nadzorni plošči IBM preverite porabljen čas in ocenite, koliko si lahko še privoščite.
  A        - glavni zagon, serija A: 40 vhodov x 4 ravni x 1 seme = 160 vezij v eni nalogi.
  B        - serija B (iste postavitve za vse ravni), 160 vezij. Samo, če ostane dovolj časa.
  prenesi  - prenese rezultate že oddane naloge (--job-id ...).
             Uporabno, če ste program prekinili med čakanjem v vrsti.

Seme prevajalnika: za vsako kombinacijo (vezje, raven) vezje prevedemo z vsemi 10 semeni in vzamemo seme
z MEDIANO števila dvokubitnih vrat. Tako na procesorju poženemo tipičen primer, ne najboljšega ali najslabšega.

Pred oddajo program izpiše povzetek in zahteva potrditev ("da").
Kvota v Open Plan je omejena (10 minut na 28 dni).

Izhodne datoteke v results/:
  hardware.csv              - P_pravilno (enak format kot noisy.csv + job_id)
  ibm_jobs.csv              - ena vrstica na nalogo (procesor, datum, ID ...)
  jobs.json                 - isto kot ibm_jobs.csv + različice paketov
  jobs/<job_id>_meta.json   - kateri indeks v nalogi je katero vezje/vhod
  jobs/<job_id>_counts.json - surovi histogrami (shranimo takoj)

Zagon:
    python src/hardware.py poskus --backend ibm_marrakesh
    python src/hardware.py A --backend ibm_marrakesh
    python src/hardware.py prenesi --job-id <ID>
    python src/hardware.py A --backend fake_marrakesh   # lokalni preizkus, brez kvote
Račun mora biti shranjen lokalno (QiskitRuntimeService.save_account). API ključa NE pišemo v kodo.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from qiskit_ibm_runtime import SamplerV2

from circuits import CIRCUITS, inputs
from simulate import calibration_date, load_layouts_B, package_versions, result_row, transpile_all_inputs
from transpile_run import LEVELS, SEEDS, RESULTS, get_backend, make_pass_manager, metrics, zero_input_circuit

SHOTS = 1000   # ponovitve na vezje na procesorju


# ---------------------------------------------------------------------
# Izbira semena z mediano števila dvokubitnih vrat
# ---------------------------------------------------------------------

def median_seed(backend, name, level, layout):
    """
    Vezje (brez priprave vhoda) prevede z vsemi semeni in vrne seme, pri katerem je število dvokubitnih vrat mediana.

    Pri 10 semenih sta na sredini dve vrednosti; vzamemo spodnjo (indeks 4 v urejenem seznamu).
    Pri enakem številu vrat ima prednost manjše seme, da je izbira ponovljiva.
    To naredimo, ker je kvota na IBM-u premajhna za 10 razlicnih semen - vzaamemo tipičen primer (mediano)
    """
    qc = zero_input_circuit(name)
    scores = []
    for seed in SEEDS:
        tqc = make_pass_manager(backend, level, seed, layout).run(qc)   # pm.run() vrne prevedeno vezje (pm ~ pass manager)
        scores.append((metrics(tqc)["st_dvokubitnih"], seed))
    scores.sort()
    return scores[(len(scores) - 1) // 2][1]


# ---------------------------------------------------------------------
# Priprava vezij za nalogo
# ---------------------------------------------------------------------

def prepare(backend, task):
    """
    Pripravi seznam prevedenih vezij za nalogo in seznam opisov (kateri indeks je katero vezje, raven, seme, vhod).
    """
    if task == "poskus":
        plan = [("toffoli", "A", 1)]           # (vezje, serija, raven)
    else:
        plan = [(name, task, level) for name in CIRCUITS for level in LEVELS]

    layouts_B = load_layouts_B(backend) if task == "B" else {}

    circuits, meta = [], []
    for name, serija, level in plan:
        layout = layouts_B.get(name)           # None pri seriji A
        seed = median_seed(backend, name, level, layout)
        for bits, tqc in transpile_all_inputs(backend, name, level, seed, layout):
            circuits.append(tqc)
            meta.append({"vezje": name, "serija": serija, "raven": level, "seme": seed, "bits": bits})
        print(f"  {name}, serija {serija}, raven {level}: seme {seed}")
    return circuits, meta, layouts_B


# ---------------------------------------------------------------------
# Zapis podatkov o nalogah
# ---------------------------------------------------------------------

def append_csv(path, new_rows, key="job_id"):
    """
    Doda vrstice v CSV. Stare vrstice z istim job_id najprej odstrani,
    da ob ponovnem prenosu iste naloge ne dobimo podvojenih vrstic.
    """
    new = pd.DataFrame(new_rows)
    if path.exists():
        # dtype=str: brez tega pandas vhod "001" prebere kot število 1
        old = pd.read_csv(path, dtype=str)
        old = old[~old[key].isin(new[key])]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(path, index=False)


def save_job_info(out, info):
    """Zapiše/posodobi podatke o nalogi v ibm_jobs.csv in jobs.json."""
    # ibm_jobs.csv: brez gnezdenih podatkov (različice, postavitve)
    flat = {k: v for k, v in info.items() if k not in ("verzije", "postavitve_B")}
    append_csv(out / "ibm_jobs.csv", [flat])

    path = out / "jobs.json"
    jobs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    jobs = [j for j in jobs if j["job_id"] != info["job_id"]]
    jobs.append(info)
    path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def job_usage(job):
    """Porabljen čas kvantnega procesorja v sekundah (če je na voljo)."""
    try:
        return job.usage()
    except Exception:
        try:
            return job.metrics()["usage"]["quantum_seconds"]
        except Exception:
            return None


# ---------------------------------------------------------------------
# Obdelava rezultatov
# ---------------------------------------------------------------------

def process_result(out, job, meta, circuits, info):
    """
    Iz rezultata naloge izračuna P_pravilno, shrani surove histograme in doda vrstice v hardware.csv.
    """
    job_id = info["job_id"]
    result = job.result()   # počaka, da se naloga konča

    # 1. surovi histogrami: shranimo TAKOJ, preden karkoli računamo
    # result[i] je rezultat i-tega vezja (PUB).
    # Register meritev se imenuje "meas", ker smo meritve dodali z measure_all().
    all_counts = [result[i].data.meas.get_counts() for i in range(len(meta))]
    (out / "jobs" / f"{job_id}_counts.json").write_text(json.dumps(all_counts, indent=2), encoding="utf-8")

    # 2. P_pravilno za vsako vezje
    rows = []
    for m, tqc, counts in zip(meta, circuits, all_counts):
        row = result_row("procesor", info["procesor"], m["vezje"], m["serija"], m["raven"], m["seme"], m["bits"],
                         tqc, counts)
        row["job_id"] = job_id
        rows.append(row)
    append_csv(out / "hardware.csv", rows)

    # 3. posodobimo podatke o nalogi (stanje, porabljen čas)
    info["status"] = str(job.status())
    info["porabljen_cas_s"] = job_usage(job)
    save_job_info(out, info)

    df = pd.DataFrame(rows)
    print(f"Zapisano: {out / 'hardware.csv'} (+{len(df)} vrstic)")
    print(f"Porabljen čas procesorja: {info['porabljen_cas_s']} s")
    print("\nPovprečni P_pravilno (procesor):")
    print(df.groupby(["vezje", "raven"])["P"].mean().unstack("raven").round(3))


# ---------------------------------------------------------------------
# Oddaja naloge
# ---------------------------------------------------------------------

def submit(args, out):
    backend = get_backend(args.backend)
    is_fake = backend.name.startswith("fake")
    print(f"Procesor: {backend.name}, kalibracija: {calibration_date(backend)}")
    print("Prevajam vezja ...")
    circuits, meta, layouts_B = prepare(backend, args.task)

    # --- potrditev pred oddajo (kvota je omejena) ---
    print(f"\nNaloga '{args.task}': {len(circuits)} vezij x {args.shots} ponovitev na {backend.name}")
    if not is_fake:
        if input("Oddam nalogo na pravi procesor? Vpišite 'da': ") != "da":
            print("Preklicano, nič ni bilo oddano.")
            return

    # --- Sampler: vrne histograme meritev ---
    # mode=backend pomeni zagon ene samostojne naloge (job mode).
    # Za fake_marrakesh Sampler vezja lokalno simulira s šumnim modelom.
    sampler = SamplerV2(mode=backend)
    sampler.options.default_shots = args.shots
    # Izklopimo vse tehnike zmanjševanja napak, da merimo "surov" vpliv prevajalnika:
    #   - dinamično razklapljanje (vstavljanje vrat v čase mirovanja),
    #   - naključno sukanje vrat in meritev (twirling).
    sampler.options.dynamical_decoupling.enable = False
    sampler.options.twirling.enable_gates = False
    sampler.options.twirling.enable_measure = False

    # Vsako vezje je en PUB (primitive unified bloc). Vseh 160 gre v eno nalogo, da čakamo v vrsti samo enkrat.
    job = sampler.run(circuits)
    job_id = job.job_id()
    print(f"Oddano. ID naloge: {job_id}")

    # --- podatke o nalogi shranimo takoj po oddaji ---
    # Če program prekinemo (ali se povezava prekine), lahko rezultate kasneje prenesemo z:
    #   python src/hardware.py prenesi --job-id ID
    (out / "jobs").mkdir(parents=True, exist_ok=True)
    meta_doc = {
        "job_id": job_id,
        "procesor": backend.name,
        "naloga": args.task,
        "vezja": meta,
    }
    (out / "jobs" / f"{job_id}_meta.json").write_text(json.dumps(meta_doc, indent=2), encoding="utf-8")
    info = {
        "job_id": job_id,
        "procesor": backend.name,
        "naloga": args.task,
        "datum_oddaje": datetime.now().isoformat(timespec="seconds"),
        "kalibracija": calibration_date(backend),
        "st_vezij": len(circuits),
        "ponovitve": args.shots,
        "status": "oddano",
        "porabljen_cas_s": None,
        "verzije": package_versions(),
        "postavitve_B": layouts_B,
    }
    save_job_info(out, info)

    print("Čakam na rezultate (Ctrl+C prekine čakanje, naloga ostane v vrsti) ...")
    process_result(out, job, meta, circuits, info)


# ---------------------------------------------------------------------
# Prenos rezultatov že oddane naloge
# se uporablja, če je program prekinjen med čakanjem v vrsti ali če želimo rezultate prenesti kasneje.
# program bi se lahko prekinil ce je cakalna vrsta predolga, ali pa je uporabnik prekinil program (Ctrl+C).
# ---------------------------------------------------------------------

def fetch(args, out):
    from qiskit_ibm_runtime import QiskitRuntimeService

    meta_doc = json.loads((out / "jobs" / f"{args.job_id}_meta.json").read_text(encoding="utf-8"))
    service = QiskitRuntimeService()
    job = service.job(args.job_id)
    status = str(job.status())
    print(f"Naloga {args.job_id}: {status}")
    if status not in ("DONE", "JobStatus.DONE"):
        print("Naloga še ni končana. Poskusite kasneje.")
        return

    # Vezja ponovno prevedemo z enakimi nastavitvami (isto seme in postavitev), da dobimo strukturne metrike
    # za hardware.csv. Prevajanje je deterministično, zato dobimo enaka vezja.
    backend = get_backend(meta_doc["procesor"])
    layouts_B = load_layouts_B(backend) if meta_doc["naloga"] == "B" else {}
    meta = meta_doc["vezja"]
    circuits = []
    done = {}   # (vezje, raven) -> seznam prevedenih vezij
    for m in meta:
        key = (m["vezje"], m["raven"])
        if key not in done:
            pairs = transpile_all_inputs(backend, m["vezje"], m["raven"], m["seme"], layouts_B.get(m["vezje"]))
            done[key] = [tqc for _, tqc in pairs]
        idx = inputs(m["vezje"]).index(m["bits"])
        circuits.append(done[key][idx])

    jobs = json.loads((out / "jobs.json").read_text(encoding="utf-8"))
    info = next(j for j in jobs if j["job_id"] == args.job_id)
    process_result(out, job, meta, circuits, info)


# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=["poskus", "A", "B", "prenesi"])
    parser.add_argument("--backend", help="ime procesorja, npr. ibm_marrakesh")
    parser.add_argument("--shots", type=int, default=SHOTS)
    parser.add_argument("--job-id", help="ID naloge (za 'prenesi')")
    parser.add_argument("--out-dir", default=None, help="mapa za rezultate")
    args = parser.parse_args()

    # Lokalni preizkus (fake_...) piše v posebno podmapo, da ne pomeša preizkusnih podatkov s pravimi.
    if args.out_dir:
        out = Path(args.out_dir)
    elif args.backend and args.backend.startswith("fake"):
        out = RESULTS / "hardware_preizkus"
    else:
        out = RESULTS
    out.mkdir(parents=True, exist_ok=True)

    if args.task == "prenesi":
        if not args.job_id:
            parser.error("za 'prenesi' podajte --job-id")
        fetch(args, out)
    else:
        if not args.backend:
            parser.error("podajte --backend (npr. ibm_marrakesh ali fake_marrakesh)")
        submit(args, out)


if __name__ == "__main__":
    main()
