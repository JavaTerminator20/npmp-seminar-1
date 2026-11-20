"""
Shrani kalibracije procesorja, ki smo jih uporabili pri poskusih.

Kalibracija = izmerjene lastnosti kubitov (napaka meritve, T1, T2) in dvokubitnih vrat (napaka CZ).
IBM jo osvežuje večkrat na dan in hrani tudi stare. Tu shranimo vse kalibracije, ki se pojavijo v naših rezultatih:
  - results/simulate/layouts_B_<procesor>.json  (iz te kalibracije smo izbrali postavitve za serijo B),
  - results/hardware/ibm_jobs.csv                (kalibracija ob prevajanju za vsako nalogo),
  - results/simulate/noisy_meta.json             (kalibracija, iz katere je zgrajen šumni model).
Tako so vse številke o kubitih, ki jih omenimo v poročilu, shranjene v results/.

Izhodna datoteka: results/hardware/kalibracija.json
  {"procesor": ..., "kalibracije": [{"cas_zahteve", "last_update_date", "uporaba", "kubiti", "povezave"}, ...]}

Zagon (potrebuje shranjen IBM račun, NE porabi časa kvantnega procesorja):
    python src/save_calibration.py
    python src/save_calibration.py --backend ibm_marrakesh --extra "2026-11-19 08:28"
IBM stare kalibracije hrani le omejen čas, zato skripto poženite čim prej po zagonu na procesorju.
"""

import argparse
import json
from datetime import datetime, timedelta

import pandas as pd

from transpile_run import RESULTS_HARDWARE, RESULTS_SIMULATE, get_backend


def collect_times(backend_name):
    """
    Zbere čase kalibracij iz naših datotek z rezultati.
    Vrne slovar {čas (niz): seznam opisov, za kaj smo to kalibracijo uporabili}.
    """
    times = {}

    def add(t, use):
        if t and str(t) != "nan":
            times.setdefault(str(t), []).append(use)

    layouts_file = RESULTS_SIMULATE / f"layouts_B_{backend_name}.json"
    if layouts_file.exists():
        add(json.loads(layouts_file.read_text(encoding="utf-8")).get("kalibracija"), "izbira postavitev B")

    jobs_file = RESULTS_HARDWARE / "ibm_jobs.csv"
    if jobs_file.exists():
        jobs = pd.read_csv(jobs_file, dtype=str)
        for _, j in jobs[jobs["procesor"] == backend_name].iterrows():
            add(j["kalibracija"], f"naloga {j['naloga']} ({j['job_id']})")

    noisy_meta = RESULTS_SIMULATE / "noisy_meta.json"
    if noisy_meta.exists():
        meta = json.loads(noisy_meta.read_text(encoding="utf-8"))
        if meta.get("procesor") == backend_name:
            add(meta.get("kalibracija"), "šumni model (simulate.py)")
    return times


def find_properties(backend, target):
    """
    Poišče kalibracijo, katere last_update_date je natanko target.

    properties(datetime=t) vrne kalibracijo, ki je bila ob času t že objavljena v zgodovini. Objava zamuja
    10-30 minut za časom meritve, zato pri t = target dobimo PREJŠNJO kalibracijo. Čas zato povečujemo
    po 5 minut, dokler ne dobimo iskane (ali že naslednje, takrat iskane v zgodovini ni).
    Vrne (props, natancno), kjer natancno pove, ali smo našli točno iskano kalibracijo.
    """
    target_dt = datetime.fromisoformat(target)
    props = None
    for minutes in range(0, 125, 5):
        props = backend.properties(datetime=target_dt + timedelta(minutes=minutes))
        if props.last_update_date == target_dt:
            return props, True
        if props.last_update_date > target_dt:
            break
    return props, False


def snapshot(props):
    """Iz objekta BackendProperties prebere lastnosti vseh kubitov in napake vrat CZ."""
    qubits = []
    for q in range(len(props.qubits)):
        def get(fn):
            # nekateri kubiti nimajo vseh podatkov (npr. izklopljen kubit), takrat zapišemo None
            try:
                return fn(q)
            except Exception:
                return None
        t1, t2 = get(props.t1), get(props.t2)
        qubits.append({
            "kubit": q,
            "napaka_meritve": get(props.readout_error),
            "T1_us": round(t1 * 1e6, 2) if t1 is not None else None,   # sekunde -> mikrosekunde
            "T2_us": round(t2 * 1e6, 2) if t2 is not None else None,
        })

    edges = []
    for g in props.gates:
        if g.gate == "cz":
            err = next((p.value for p in g.parameters if p.name == "gate_error"), None)
            edges.append({"kubita": list(g.qubits), "napaka_cz": err})
    return qubits, edges


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="ibm_marrakesh")
    parser.add_argument("--extra", nargs="*", default=[],
                        help="dodatni časi, npr. \"2026-11-19 08:28\" (lokalni čas, UTC+1)")
    args = parser.parse_args()

    backend = get_backend(args.backend)
    times = collect_times(backend.name)
    for t in args.extra:
        times.setdefault(t + ":00+01:00" if len(t) == 16 else t, []).append("dodatno (--extra)")

    out = []
    for t, uses in sorted(times.items()):
        props, exact = find_properties(backend, t)
        qubits, edges = snapshot(props)
        out.append({
            "cas_zahteve": t,
            "last_update_date": str(props.last_update_date),
            "natancno": exact,   # False: iskane kalibracije v zgodovini ni, shranjena je najbližja
            "uporaba": uses,
            "kubiti": qubits,
            "povezave": edges,
        })
        mark = "" if exact else "  POZOR: ni natančnega ujemanja"
        print(f"  {t} -> kalibracija {props.last_update_date} ({', '.join(uses)}){mark}")

    path = RESULTS_HARDWARE / "kalibracija.json"
    path.write_text(json.dumps({
        "procesor": backend.name,
        "preneseno": datetime.now().isoformat(timespec="seconds"),
        "kalibracije": out,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Zapisano: {path} ({len(out)} kalibracij)")


if __name__ == "__main__":
    main()
