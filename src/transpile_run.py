"""
Prevajanje vezij in strukturne metrike (faza 2).

Za vsako vezje, raven optimizacije (0-3), seme in serijo (A/B) vezje prevedemo za ciljni procesor in zapišemo:
število kubitov, število dvokubitnih vrat, globino, število vrat in čas prevajanja.

  Serija A: privzeto prevajanje (prevajalnik sam izbere postavitev).
  Serija B: vse ravni dobijo isto začetno postavitev (initial_layout), ki jo enkrat izberemo za vsako vezje.
            Tako ločimo vpliv postavitve od vpliva optimizacije vrat.

Strukturne metrike so enake za vse vhode istega vezja, ker se vhodi razlikujejo samo v vratih X pred
barrierjem. Zato tu prevajamo vezje z ničelnim vhodom (brez vrat X).

Izhodne datoteke v results/transpile_run/:
  structural.csv  - metrike za vse kombinacije
  layouts_B.json  - postavitve za serijo B (uporabi jih tudi simulate.py)
  passes.txt      - seznam prehodov za vsako raven optimizacije
  passes_diff.txt - razlika prehodov vsake ravni od prejšnje

Zagon:
    python src/transpile_run.py                      # FakeMarrakesh
    python src/transpile_run.py --backend ibm_fez    # pravi backend
Prevajanje za pravi backend ne porabi časa kvantnega procesorja, potrebuje pa shranjen IBM račun (save_account).
"""

import argparse
import difflib
import json
import time
from pathlib import Path

import pandas as pd
from qiskit import transpile
from qiskit.transpiler import generate_preset_pass_manager

# CIRCUITS: seznam imen vezij, build(ime, vhod): zgradi vezje, inputs(ime): seznam vseh vhodov (vsak je seznam bitov)
from circuits import CIRCUITS, build, inputs

# Mapa results/ je na isti ravni kot src/ (githubRepo/results).
# Pot računamo od te datoteke, da skripta deluje iz katerekoli mape.
RESULTS = Path(__file__).resolve().parent.parent / "results"
# Vsaka skripta piše v svojo podmapo results/<ime skripte>/.
RESULTS_TRANSPILE = RESULTS / "transpile_run"
RESULTS_SIMULATE = RESULTS / "simulate"
RESULTS_HARDWARE = RESULTS / "hardware"
RESULTS_ANALYZE = RESULTS / "analyze"

LEVELS = [0, 1, 2, 3]     # ravni optimizacije, ki jih primerjamo
# Prevajalnik pri postavitvi in usmerjanju uporablja naključje (algoritem Sabre).
# Z več semeni dobimo povprečje in raztros, s fiksnimi semeni pa ponovljive rezultate.
SEEDS = list(range(10))   # semena 0..9 za seed_transpiler


# ---------------------------------------------------------------------
# Ciljni procesor
# ---------------------------------------------------------------------

def get_backend(name):
    """
    Vrne ciljni procesor.
    "fake_marrakesh" je lokalna kopija procesora ibm_marrakesh (povezljivost in kalibracija sta shranjeni
    v Qiskitu), zato ne potrebuje računa. Za drugo ime se poveže na IBM z lokalno shranjenim računom.
    """
    # Uvoza sta znotraj funkcije, da se povezava na IBM vzpostavi le, kadar jo res potrebujemo.
    if name == "fake_marrakesh":
        from qiskit_ibm_runtime.fake_provider import FakeMarrakesh
        return FakeMarrakesh()
    from qiskit_ibm_runtime import QiskitRuntimeService
    # QiskitRuntimeService() prebere račun, shranjen s save_account
    return QiskitRuntimeService().backend(name)


def two_qubit_gate_name(backend):
    """Ime osnovnih dvokubitnih vrat procesorja (cz, ecr ali cx)."""
    # target.operation_names = vsa vrata, ki jih procesor zna izvesti.
    # Novejši procesorji (Heron, npr. Marrakesh) imajo cz, starejši (Eagle) ecr, simulatorji pogosto cx.
    for name in ["cz", "ecr", "cx"]:
        if name in backend.target.operation_names:
            return name
    raise ValueError("Procesor nima znanih dvokubitnih vrat.")


# ---------------------------------------------------------------------
# Serija B: izbira povezanih kubitov z majhnimi napakami
# ---------------------------------------------------------------------

def choose_layout_B(backend, n):
    """
    Izbere n povezanih fizičnih kubitov z majhnimi napakami.

    Preprost požrešni postopek:
      1. začnemo pri vsakem fizičnem kubitu posebej,
      2. dodajamo soseda, pri katerem je vsota napake dvokubitnih vrat (do že izbranega kubita)
         in napake meritve najmanjša,
      3. ko imamo n kubitov, izračunamo skupno napako,
      4. vzamemo izbiro z najmanjšo skupno napako.

    Vrne seznam fizičnih kubitov: logični kubit i -> fizični kubit [i].
    """
    # target vsebuje povezljivost čipa in kalibracijske podatke (napake vrat in meritev za vsak kubit oz. par)
    target = backend.target
    gate = two_qubit_gate_name(backend)

    # --- 1. korak: napake povezav in sosedi vsakega kubita ---
    # target[gate] je slovar {(q1, q2): lastnosti vrat na tem paru}. Vsak par v slovarju je povezava na čipu.
    edge_error = {}                                           # {povezava: napaka}
    neighbors = {q: set() for q in range(target.num_qubits)}  # {kubit: sosedi}
    for (q1, q2), props in target[gate].items():
        # če podatka o napaki ni, vzamemo 1.0 (najslabše), da se algoritem takšni povezavi izogne
        err = props.error if props is not None and props.error is not None else 1.0
        # frozenset: (3, 4) in (4, 3) sta ista povezava. Če sta smeri zapisani posebej, obdržimo manjšo napako.
        key = frozenset((q1, q2))
        edge_error[key] = min(err, edge_error.get(key, 1.0))
        neighbors[q1].add(q2)
        neighbors[q2].add(q1)

    # --- 2. korak: napake meritve posameznih kubitov ---
    # target["measure"] je slovar {(q,): lastnosti meritve na kubitu q}
    readout_error = {}
    for q in range(target.num_qubits):
        props = target["measure"].get((q,))
        readout_error[q] = props.error if props is not None and props.error is not None else 1.0

    # --- 3. korak: požrešno iskanje od vsakega začetnega kubita ---
    best_layout = None   # najboljša najdena skupina kubitov
    best_score = None    # njena skupna napaka (manjša je boljša)
    for start in range(target.num_qubits):
        chosen = [start]
        score = readout_error[start]
        # skupino širimo za enega soseda naenkrat, dokler nima n kubitov
        while len(chosen) < n:
            # kandidati so vsi še neizbrani sosedi že izbranih kubitov;
            # cena = napaka povezave do izbranega kubita + napaka meritve
            candidates = []
            for c in chosen:
                for nb in neighbors[c]:
                    if nb not in chosen:
                        cost = edge_error[frozenset((c, nb))] + readout_error[nb]
                        candidates.append((cost, nb))
            if not candidates:
                break            # ni več sosedov (izoliran del čipa)
            # min nad pari (cena, kubit) vrne par z najmanjšo ceno
            cost, nb = min(candidates)
            chosen.append(nb)
            score += cost
        # obdržimo skupino, če je polna in boljša od dosedanje najboljše
        if len(chosen) == n and (best_score is None or score < best_score):
            best_layout = chosen
            best_score = score
    # Opomba: postopek je požrešen (v vsakem koraku vzame trenutno najcenejšega soseda),
    # zato ne zagotavlja globalno najboljše izbire.
    return best_layout


# ---------------------------------------------------------------------
# Prevajanje in metrike
# ---------------------------------------------------------------------

def make_pass_manager(backend, level, seed, layout=None):
    """Upravljalnik prehodov za dano raven. Uporabi ga tudi simulate.py."""
    # Upravljalnik prehodov (pass manager) je zaporedje korakov prevajanja: postavitev, usmerjanje,
    # razgradnja v osnovna vrata in optimizacija. Katere korake vsebuje, določa raven.
    # layout=None: postavitev izbere prevajalnik (serija A), sicer uporabi podani seznam fizičnih kubitov (serija B).
    return generate_preset_pass_manager(
        optimization_level=level,
        backend=backend,
        seed_transpiler=seed,
        initial_layout=layout,
    )


def metrics(qc):
    """Strukturne metrike prevedenega vezja (barrierje ignoriramo)."""
    used_qubits = set()  # indeksi fizičnih kubitov, ki jih vezje uporabi
    n_2q = 0             # število dvokubitnih vrat
    n_gates = 0          # število vseh vrat (brez meritev)
    # qc.data je seznam vseh ukazov v vezju po vrsti
    for inst in qc.data:
        name = inst.operation.name
        # barrier in delay nista prava vrata, zato ju preskočimo
        if name in ("barrier", "delay"):
            continue
        # kubit, na katerem deluje ukaz, štejemo kot uporabljen (tudi pri meritvi)
        for q in inst.qubits:
            used_qubits.add(qc.find_bit(q).index)
        if name == "measure":
            continue              # meritve ne štejemo med vrata
        n_gates += 1
        if len(inst.qubits) == 2:
            n_2q += 1
    # globina = dolžina najdaljše verige ukazov, ki si morajo slediti; barrierji je ne smejo podaljšati
    depth = qc.depth(filter_function=lambda inst: inst.operation.name != "barrier")
    return {
        "st_kubitov": len(used_qubits),
        "st_dvokubitnih": n_2q,
        "globina": depth,
        "st_vrat": n_gates,
    }


def zero_input_circuit(name):
    """Vezje z vhodom 0...0, torej brez vrat X (samo jedro in meritve)."""
    # dolžina prvega vhoda = število vhodnih bitov vezja
    n = len(inputs(name)[0])
    return build(name, [0] * n)


def before_metrics(name, print_circuit=False):
    """
    Metrike pred prevajanjem za procesor ("raven = pred" v structural.csv).
    Toffolijevih in Fredkinovih vrat ne moremo neposredno šteti kot dvokubitna vrata, zato vezje razgradimo
    na CNOT in enokubitna vrata BREZ omejitev povezljivosti in brez optimizacije. To je izhodišče,
    primerljivo z literaturo (npr. 6 CNOT za Toffolija).
    """
    # Brez argumenta backend prevajalnik ne pozna povezljivosti, zato ne dodaja vrat SWAP.
    # "u" je splošna enokubitna vrata.
    qc = transpile(zero_input_circuit(name), basis_gates=["cx", "u"], optimization_level=0, seed_transpiler=0)

    if print_circuit:
        print(qc.draw())

    return metrics(qc)


# ---------------------------------------------------------------------
# Seznam prehodov za vsako raven (za opis ravni v Metodah)
# ---------------------------------------------------------------------

# Parametri, ki jih izpišemo ob imenu prehoda. Ravni se pri teh prehodih ne razlikujejo po imenu,
# ampak po nastavitvah (npr. več poskusov na višji ravni). Seme izpustimo, ker je povsod enako.
PASS_PARAMS = {
    "SabreLayout": ["max_iterations", "layout_trials", "swap_trials"],
    "SabreSwap": ["heuristic", "trials"],
}


def pass_names(task):
    """
    Rekurzivno pobere imena prehodov iz (gnezdenih) kontrolerjev.
    Pri prehodih iz PASS_PARAMS ime dopolni s parametri, npr. "SabreSwap(heuristic=decay, trials=5)".
    """
    # Kontroler (npr. zanka "ponavljaj, dokler se vezje spreminja") ima atribut tasks s seznamom
    # notranjih prehodov ali kontrolerjev. Opomba: pogoje in zanke kontrolerjev tu izgubimo.
    if hasattr(task, "tasks"):
        names = []
        for t in task.tasks:
            names += pass_names(t)
        return names
    # posamezen prehod: ime njegovega razreda (npr. "SabreLayout")
    name = type(task).__name__
    if name in PASS_PARAMS:
        params = ", ".join(f"{p}={getattr(task, p, '?')}" for p in PASS_PARAMS[name])
        name += f"({params})"
    return [name]


def stage_passes(backend, level):
    """Vrne slovar {faza: seznam imen prehodov} za dano raven."""
    pm = make_pass_manager(backend, level, seed=0)
    stages = {}
    # pm.stages: imena faz prevajanja, npr. init, layout, routing, translation, optimization, scheduling
    for stage in pm.stages:
        stage_pm = getattr(pm, stage)
        if stage_pm is None:
            continue              # faza na tej ravni ni nastavljena
        stages[stage] = pass_names(stage_pm.to_flow_controller())
    return stages


def diff_lines(old, new):
    """
    Razlika med dvema seznamoma prehodov (difflib ohrani vrstni red).
    Vrne vrstice z "+" (dodano) in "-" (odvzeto).
    """
    lines = []
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    # opcode: (vrsta, i1, i2, j1, j2); old[i1:i2] se spremeni v new[j1:j2]
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            lines.append("- " + ", ".join(old[i1:i2]))
        if tag in ("insert", "replace"):
            # mesto vstavitve: za katerim prehodom nove ravni
            where = f"  (za {new[j1 - 1]})" if j1 > 0 else "  (na začetku)"
            lines.append("+ " + ", ".join(new[j1:j2]) + where)
    return lines


def write_passes(backend, path, diff_path):
    """
    path:      celoten seznam prehodov za vsako raven
    diff_path: razlika vsake ravni od prejšnje (raven 0 v celoti)
    """
    all_levels = {level: stage_passes(backend, level) for level in LEVELS}

    # --- celoten seznam ---
    lines = []
    for level, stages in all_levels.items():
        lines.append(f"=== raven optimizacije {level} ===")
        for stage, names in stages.items():
            lines.append(f"  [{stage}] " + ", ".join(names))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")

    # --- razlike od prejšnje ravni ---
    lines = []
    prev = None
    for level, stages in all_levels.items():
        if prev is None:
            lines.append(f"=== raven optimizacije {level} (vsi prehodi) ===")
            for stage, names in stages.items():
                lines.append(f"  [{stage}] " + ", ".join(names))
        else:
            lines.append(f"=== raven optimizacije {level} (razlika od ravni {level - 1}) ===")
            unchanged = []
            # unija faz obeh ravni, v vrstnem redu, kot nastopajo
            for stage in list(dict.fromkeys([*prev, *stages])):
                d = diff_lines(prev.get(stage, []), stages.get(stage, []))
                if not d:
                    unchanged.append(stage)
                    continue
                lines.append(f"  [{stage}]")
                lines += [f"    {x}" for x in d]
            if unchanged:
                lines.append("  brez sprememb: " + ", ".join(unchanged))
        lines.append("")
        prev = stages
    diff_path.write_text("\n".join(lines), encoding="utf-8")


'''
  GLAVNA ZANKA:
1. preberi ime procesorja iz ukazne vrstice
2. zapiši passes.txt
3. za vsako vezje izberi postavitev B → layouts_B.json
4. za vsako vezje:
       dodaj vrstico "pred"
       za serijo A in B:
           za raven 0, 1, 2, 3:
               za seme 0..9:
                   prevedi, izmeri čas, izračunaj metrike → nova vrstica
5. vse vrstice zapiši v structural.csv
6. izpiši tabelo povprečnega števila dvokubitnih vrat
'''

def main():
    # ime procesorja lahko podamo v ukazni vrstici (--backend ...)
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="fake_marrakesh")
    args = parser.parse_args()

    out = RESULTS_TRANSPILE
    out.mkdir(parents=True, exist_ok=True)
    backend = get_backend(args.backend)
    print(f"Ciljni procesor: {backend.name}")

    # 1. seznam prehodov po ravneh -> passes.txt, razlike med ravnmi -> passes_diff.txt
    write_passes(backend, out / "passes.txt", out / "passes_diff.txt")

    # 2. postavitve za serijo B (enkrat na vezje). Shranimo jih v JSON, da simulate.py uporabi iste kubite.
    layouts_B = {}
    for name in CIRCUITS:
        n = len(inputs(name)[0])
        layouts_B[name] = choose_layout_B(backend, n)
    with open(out / "layouts_B.json", "w", encoding="utf-8") as f:
        json.dump({"backend": backend.name, "layouts": layouts_B}, f, indent=2)

    # 3. prevajanje vseh kombinacij; vsaka kombinacija je ena vrstica (slovar),
    # na koncu iz seznama vrstic naredimo tabelo
    rows = []
    for name in CIRCUITS:
        # metrike pred prevajanjem (ena vrstica na vezje)
        rows.append({"vezje": name, "serija": "-", "raven": "pred", "seme": "", **before_metrics(name), "cas_s": ""})

        qc = zero_input_circuit(name)
        for serija in ["A", "B"]:
            layout = None if serija == "A" else layouts_B[name]
            for level in LEVELS:
                for seed in SEEDS:
                    pm = make_pass_manager(backend, level, seed, layout)
                    # merimo samo čas samega prevajanja (pm.run)
                    t0 = time.perf_counter()
                    tqc = pm.run(qc)
                    elapsed = time.perf_counter() - t0
                    # **metrics(tqc) razširi slovar metrik v stolpce vrstice
                    rows.append({"vezje": name, "serija": serija, "raven": level, "seme": seed,
                                 **metrics(tqc), "cas_s": round(elapsed, 4)})
        print(f"  {name}: končano")

    # 4. zapis tabele: 4 vezja x (1 "pred" + 2 seriji x 4 ravni x 10 semen)
    df = pd.DataFrame(rows)
    df.to_csv(out / "structural.csv", index=False)
    print(f"Zapisano: {out / 'structural.csv'} ({len(df)} vrstic)")

    # 5. kratek povzetek: povprečno število dvokubitnih vrat čez semena (vrstice = vezje in serija, stolpci = raven)
    summary = df[df["raven"] != "pred"].groupby(["vezje", "serija", "raven"])["st_dvokubitnih"].mean().unstack("raven")
    print("\nPovprečno število dvokubitnih vrat:")
    print(summary.round(1))


if __name__ == "__main__":
    main()
    #print(before_metrics("fredkin", True))  # test, da se koda ne zlomi
