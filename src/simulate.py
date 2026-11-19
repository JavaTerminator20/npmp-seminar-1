"""
Simulacije: idealni in šumni simulator (faza 3).

Postopek:
  1. Za vsako vezje, serijo (A/B), raven optimizacije (0-3) in seme prevedemo VSE vhode za ciljni procesor
     (isti upravljalnik prehodov kot v transpile_run.py).
  2. Idealni simulator (brez šuma) požene prevedena vezja s semenom 0. To je kontrola: P_pravilno mora biti
     1.0 na vseh ravneh. Če ni, je prevajalnik (ali naša koda) pokvaril vezje.
  3. Šumni simulator (šumni model iz kalibracije procesorja) požene vsa prevedena vezja:
     40 vhodov x 4 ravni x 10 semen x 2 seriji = 3200 vezij.
  4. Za vsak zagon izračunamo P_pravilno = (število pravilnih izhodov) / (število ponovitev).

Izhodne datoteke v results/simulate/:
  ideal.csv          - kontrola na idealnem simulatorju
  noisy.csv          - P_pravilno na šumnem simulatorju (ena vrstica na vezje)
  noisy_counts.json  - surovi histogrami šumnega simulatorja
  noisy_meta.json    - procesor, datum kalibracije, ponovitve, različice

Zagon:
    python src/simulate.py                          # šumni model iz FakeMarrakesh
    python src/simulate.py --backend ibm_marrakesh  # šumni model iz pravega procesorja (današnja kalibracija)
    python src/simulate.py --seeds 2 --shots 500    # hiter preizkus

Za končne rezultate šumni model zgradimo iz pravega procesorja na dan zagona na procesorju (hardware.py),
da sta oba iz iste kalibracije. Pridobivanje kalibracije NE porabi časa kvantnega procesorja.
"""

import argparse
import json
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import pandas as pd
from qiskit_aer import AerSimulator

# build(ime, vhod): celotno vezje za en vhod (X, barrier, jedro, meritve)
# expected(ime, vhod): pričakovani izhod v Qiskitovem vrstnem redu
# to_qiskit_string(vhod): seznam bitov -> niz, kot ga izpiše Qiskit
from circuits import CIRCUITS, build, expected, inputs, to_qiskit_string
# iste funkcije kot pri strukturnih metrikah, da je prevajanje enako
from transpile_run import LEVELS, SEEDS, RESULTS_SIMULATE, RESULTS_TRANSPILE, choose_layout_B, get_backend, make_pass_manager, metrics

SERIES = ["A", "B"]
SHOTS_NOISY = 2000      # ponovitve na vezje pri šumnem simulatorju
SHOTS_IDEAL = 1000      # ponovitve pri idealnem simulatorju (kontrola)
# Seme simulatorja: Aer pri meritvah žreba izide. S fiksnim semenom dobimo ob ponovnem zagonu enake histograme.
SEED_SIMULATOR = 12345


# ---------------------------------------------------------------------
# Pomožne funkcije (uporablja jih tudi hardware.py)
# ---------------------------------------------------------------------

def package_versions():
    """Različice paketov, ki jih zapišemo ob rezultatih."""
    return {p: version(p) for p in ["qiskit", "qiskit-aer", "qiskit-ibm-runtime"]}


def calibration_date(backend):
    """
    Datum zadnje kalibracije procesorja (kdaj so bile izmerjene napake vrat in meritev).
    Če ga ni mogoče dobiti, vrne None.
    """
    try:
        return str(backend.properties().last_update_date)
    except Exception:
        return None


def load_layouts_B(backend):
    """
    Vrne postavitve za serijo B: {vezje: [fizični kubiti]}.

    - Če results/transpile_run/layouts_B.json ustreza temu procesorju (ga je zapisal transpile_run.py), uporabimo te
      postavitve, da so iste kot v structural.csv.
    - Sicer pogledamo results/simulate/layouts_B_<procesor>.json.
    - Če tudi te ni, postavitve izračunamo iz trenutne kalibracije in jih shranimo. Tako simulate.py
      in hardware.py na istem procesorju uporabita iste kubite.
    """
    main_file = RESULTS_TRANSPILE / "layouts_B.json"
    if main_file.exists():
        data = json.loads(main_file.read_text(encoding="utf-8"))
        if data["backend"] == backend.name:
            return data["layouts"]

    own_file = RESULTS_SIMULATE / f"layouts_B_{backend.name}.json"
    if own_file.exists():
        return json.loads(own_file.read_text(encoding="utf-8"))["layouts"]

    print(f"  Postavitve za serijo B na {backend.name} še ne obstajajo, izračunam jih iz trenutne kalibracije.")
    layouts = {name: choose_layout_B(backend, len(inputs(name)[0])) for name in CIRCUITS}
    own_file.parent.mkdir(parents=True, exist_ok=True)
    own_file.write_text(json.dumps({
        "backend": backend.name,
        "kalibracija": calibration_date(backend),
        "layouts": layouts,
    }, indent=2), encoding="utf-8")
    return layouts


def transpile_all_inputs(backend, name, level, seed, layout):
    """
    Prevede vezje za VSE vhode z enakimi nastavitvami. Vrne seznam parov (vhod, prevedeno vezje).

    Barrier za vrati X poskrbi, da prevajalnik vrat X ne zlije z jedrom vezja,
    zato je jedro po prevajanju enako za vse vhode.
    """
    pm = make_pass_manager(backend, level, seed, layout)
    all_inputs = inputs(name)

    # pm.run sprejme seznam vezij in vrne seznam prevedenih vezij (v istem vrstnem redu)
    circuits = pm.run([build(name, bits) for bits in all_inputs])
    return list(zip(all_inputs, circuits))


def p_correct(counts, want):
    """
    P_pravilno = število pravilnih izhodov / število ponovitev.
    counts je histogram {izhod: kolikokrat}, want pričakovani izhod.
    """
    shots = sum(counts.values())
    return counts.get(want, 0) / shots


def result_row(platforma, procesor, name, serija, level, seed, bits, tqc, counts):
    """
    Ena vrstica rezultatov. Enak format uporabljajo ideal.csv, noisy.csv in hardware.csv,
    da jih analyze.py lahko združi.
    """
    want = expected(name, bits)
    m = metrics(tqc)   # strukturne metrike TEGA prevedenega vezja
    return {
        "platforma": platforma,          # idealno / sumni_model / procesor
        "procesor": procesor,            # ime procesorja (ali šumnega modela)
        "vezje": name,
        "serija": serija,
        "raven": level,
        "seme": seed,
        "vhod": to_qiskit_string(bits),  # vhod v Qiskitovem vrstnem redu
        "pricakovano": want,
        "ponovitve": sum(counts.values()),
        "P": p_correct(counts, want),
        "st_dvokubitnih": m["st_dvokubitnih"],
        "globina": m["globina"],
    }


'''
GLAVNI PROGRAM
1. Ustvari dva simulatorja:
   - AerSimulator() je idealen, brez šuma.
   - AerSimulator.from_backend(backend) iz kalibracije procesorja prebere napake vrat, napake meritev, T1/T2,
        povezljivost in osnovna vrata. Iz tega zgradi šumni model.
2. Zanka gre čez vezje x serija x raven x seme. Za vsako kombinacijo:
   - prevede vse vhode,
   - šumni simulator jih požene v enem klicu run(seznam), Aer pa jih simulira vzporedno,
   - idealni simulator požene samo seme 0, kot kontrolo. Tako preveriš, da prevedeno vezje z vstavljenimi SWAP
        in optimizacijami še vedno računa pravilno. To je močnejša kontrola od testa v circuits.py, ker preverja prevedena vezja.
3. Prevedeno vezje je zapisano na vseh 133 fizičnih kubitih. Aer neuporabljene kubite sam odstrani, zato simulira le 3-6 kubitov in je hiter.
4. Na koncu zapiše:
   - noisy.csv: 3200 vrstic,
   - ideal.csv: 320 vrstic,
   - noisy_counts.json: surovi histogrami, za graf po posameznih vhodih,
   - noisy_meta.json: procesor, datum kalibracije, ponovitve, semena, postavitve B in različice.
5. Izpiše opozorilo, če kakšno vezje na idealnem simulatorju ni dalo 100 %. Nato izpiše tabelo povprečnih P_pravilno.
'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="fake_marrakesh", help="procesor, iz katerega zgradimo šumni model")
    parser.add_argument("--shots", type=int, default=SHOTS_NOISY)
    parser.add_argument("--seeds", type=int, default=len(SEEDS), help="število semen prevajalnika (0..n-1)")
    parser.add_argument("--out-dir", default=str(RESULTS_SIMULATE), help="mapa za izhodne datoteke")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    seeds = list(range(args.seeds))

    backend = get_backend(args.backend)
    print(f"Ciljni procesor: {backend.name}, kalibracija: {calibration_date(backend)}")

    # Idealni simulator: brez šuma, poljubna povezljivost.
    ideal_sim = AerSimulator(seed_simulator=SEED_SIMULATOR)

    # Šumni simulator: from_backend prebere iz procesorja
    #   - napake in trajanje enokubitnih in dvokubitnih vrat,
    #   - napake meritev,
    #   - čase T1 in T2 (razpad stanja kubita),
    #   - povezljivost in osnovna vrata.
    # Iz tega zgradi šumni model, ki ga Aer uporabi pri simulaciji.
    noisy_sim = AerSimulator.from_backend(backend, seed_simulator=SEED_SIMULATOR)
    # Opomba: prevedeno vezje je zapisano na vseh 133 fizičnih kubitih, Aer pa samodejno odstrani kubite,
    # ki jih vezje ne uporablja, zato simulira le 3-6 kubitov in je hiter.

    layouts_B = load_layouts_B(backend)

    ideal_rows, noisy_rows, noisy_counts = [], [], []
    t_start = time.perf_counter()

    for name in CIRCUITS:
        for serija in SERIES:
            # serija A: postavitev izbere prevajalnik, serija B: vse ravni dobijo isto postavitev
            layout = None if serija == "A" else layouts_B[name]
            for level in LEVELS:
                for seed in seeds:
                    pairs = transpile_all_inputs(backend, name, level, seed, layout)
                    circuits = [tqc for _, tqc in pairs]

                    # --- šumni simulator: vsi vhodi v enem klicu (Aer vezja iz seznama simulira vzporedno) ---
                    res = noisy_sim.run(circuits, shots=args.shots).result()
                    for i, (bits, tqc) in enumerate(pairs):
                        counts = res.get_counts(i)
                        noisy_rows.append(result_row("sumni_model", backend.name, name, serija, level, seed, bits, tqc, counts))
                        noisy_counts.append({
                            "vezje": name,
                            "serija": serija,
                            "raven": level,
                            "seme": seed,
                            "vhod": to_qiskit_string(bits),
                            "counts": counts,
                        })

                    # --- idealni simulator: samo seme 0 (kontrola) ---
                    # Preverimo, da prevedeno vezje (z vrati SWAP in optimizacijami) še vedno računa pravilno.
                    if seed == seeds[0]:
                        res = ideal_sim.run(circuits, shots=SHOTS_IDEAL).result()
                        for i, (bits, tqc) in enumerate(pairs):
                            ideal_rows.append(result_row("idealno", "AerSimulator", name, serija, level, seed, bits, tqc, res.get_counts(i)))
            print(f"  {name}, serija {serija}: končano ({time.perf_counter() - t_start:.0f} s)")

    # --- zapis rezultatov ---
    ideal = pd.DataFrame(ideal_rows)
    noisy = pd.DataFrame(noisy_rows)
    ideal.to_csv(out / "ideal.csv", index=False)
    noisy.to_csv(out / "noisy.csv", index=False)
    (out / "noisy_counts.json").write_text(json.dumps(noisy_counts, indent=2), encoding="utf-8")
    (out / "noisy_meta.json").write_text(json.dumps({
        "procesor": backend.name,
        "kalibracija": calibration_date(backend),
        "datum_simulacije": datetime.now().isoformat(timespec="seconds"),
        "ponovitve": args.shots,
        "ponovitve_idealno": SHOTS_IDEAL,
        "semena_prevajalnika": seeds,
        "seed_simulator": SEED_SIMULATOR,
        "postavitve_B": layouts_B,
        "verzije": package_versions(),
    }, indent=2), encoding="utf-8")
    print(f"Zapisano: {out / 'noisy.csv'} ({len(noisy)} vrstic), {out / 'ideal.csv'} ({len(ideal)} vrstic)")

    # --- kontrola idealnega simulatorja ---
    bad = ideal[ideal["P"] < 1.0]
    if bad.empty:
        print("Idealni simulator: vsa prevedena vezja dajo P = 1.0")
    else:
        print(f"POZOR: {len(bad)} vezij na idealnem simulatorju ni pravilnih:")
        print(bad[["vezje", "serija", "raven", "vhod", "P"]])

    # --- kratek povzetek: povprečni P_pravilno čez vhode in semena ---
    summary = noisy.groupby(["vezje", "serija", "raven"])["P"].mean().unstack("raven")
    print("\nPovprečni P_pravilno (šumni model):")
    print(summary.round(3))

from qiskit_ibm_runtime import QiskitRuntimeService

if __name__ == "__main__":
    main()
    #print(package_versions())
    #print("ibm_fez instance:", calibration_date(get_backend("ibm_fez")))
    #print("ibm_kingston instance:", calibration_date(get_backend("ibm_kingston")))
    #print("ibm_marrakesh instance:", calibration_date(get_backend("ibm_marrakesh")))
    #load_layouts_B(get_backend("fake_marrakesh"))


    # from qiskit_ibm_runtime import QiskitRuntimeService

    # service = QiskitRuntimeService()
    # for b in service.backends(simulator=False, operational=True):
    #     s = b.status()
    #     print(b.name, s.pending_jobs, s.status_msg)

