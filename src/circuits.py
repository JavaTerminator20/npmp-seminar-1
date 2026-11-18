"""
Definicije reverzibilnih vezij in pričakovanih izhodov.

Za vsako vezje imamo:
  - jedro vezja (samo vrata, brez priprave vhoda in meritev),
  - seznam vseh vhodov,
  - funkcijo, ki klasično izračuna pričakovani izhod.

Vhod je zapisan kot seznam bitov, kjer je bits[i] začetna vrednost
kubita i. Primer: bits = [1, 0, 1] pomeni q0 = 1, q1 = 0, q2 = 1.

POZOR, vrstni red bitov: Qiskit izpiše rezultat meritve od zadnjega
kubita proti prvemu. Za q0 = 1, q1 = 0, q2 = 0 dobimo niz "001".
Zato funkcija to_qiskit_string() seznam bitov obrne.

Zagon (test na idealnem simulatorju, vseh 40 vhodov):
    python src/circuits.py
"""

from itertools import product

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator


# ---------------------------------------------------------------------
# Pomožne funkcije
# ---------------------------------------------------------------------

def to_qiskit_string(bits):
    """Seznam bitov [q0, q1, ...] pretvori v niz, kot ga izpiše Qiskit."""
    return "".join(str(b) for b in reversed(bits))


def int_to_bits(value, n):
    """Število pretvori v n bitov, najnižji bit je prvi: 6 -> [0, 1, 1]."""
    return [(value >> i) & 1 for i in range(n)]


def bits_to_int(bits):
    """Obratno kot int_to_bits: [0, 1, 1] -> 6."""
    return sum(b << i for i, b in enumerate(bits))


# ---------------------------------------------------------------------
# 1) Toffoli: q0 = a, q1 = b, q2 = c
#    Izhod: c postane c XOR (a AND b), a in b ostaneta.
# ---------------------------------------------------------------------

def toffoli_core():
    qc = QuantumCircuit(3)
    qc.ccx(0, 1, 2)
    return qc


def toffoli_inputs():
    # vseh 8 kombinacij treh bitov
    return [list(bits) for bits in product([0, 1], repeat=3)]


def toffoli_expected(bits):
    a, b, c = bits
    return [a, b, c ^ (a & b)]


# ---------------------------------------------------------------------
# 2) Fredkin: q0 = kontrolni bit, q1 in q2 = bita, ki ju zamenjamo
#    Če je kontrolni bit 1, se q1 in q2 zamenjata.
# ---------------------------------------------------------------------

def fredkin_core():
    qc = QuantumCircuit(3)
    qc.cswap(0, 1, 2)
    return qc


def fredkin_inputs():
    return [list(bits) for bits in product([0, 1], repeat=3)]


def fredkin_expected(bits):
    c, x, y = bits
    if c == 1:
        return [c, y, x]
    return [c, x, y]


# ---------------------------------------------------------------------
# 3) Polni seštevalnik: q0 = a, q1 = b, q2 = c_in, q3 = 0 (pomožni kubit)
#
#    Gradnja iz dveh Toffolijevih in dveh CNOT vrat:
#      Toffoli(a, b -> q3)     q3 = a·b
#      CNOT(a -> b)            q1 = a XOR b
#      Toffoli(b, c_in -> q3)  q3 = a·b XOR (a XOR b)·c_in = prenos
#      CNOT(b -> c_in)         q2 = a XOR b XOR c_in = vsota
#
#    Izhod: q0 = a, q1 = a XOR b, q2 = vsota, q3 = prenos (c_out)
# ---------------------------------------------------------------------

def full_adder_core():
    qc = QuantumCircuit(4)
    qc.ccx(0, 1, 3)
    qc.cx(0, 1)
    qc.ccx(1, 2, 3)
    qc.cx(1, 2)
    return qc


def full_adder_inputs():
    # a, b, c_in imajo vse kombinacije, pomožni kubit q3 je vedno 0
    return [list(bits) + [0] for bits in product([0, 1], repeat=3)]


def full_adder_expected(bits):
    a, b, c_in, _ = bits
    total = a + b + c_in           # navadno seštevanje števil 0..3
    vsota = total % 2
    prenos = total // 2
    return [a, a ^ b, vsota, prenos]


# ---------------------------------------------------------------------
# 4) 2-bitni Cuccarov seštevalnik (Cuccaro idr., 2004)
#
#    Razporeditev kubitov (kot v članku):
#      q0 = c0 (vhodni prenos, vedno 0)
#      q1 = b0, q2 = a0   (najnižja bita števil b in a)
#      q3 = b1, q4 = a1   (višja bita)
#      q5 = z  (izhodni prenos, začne z 0)
#
#    Po izvedbi: a ostane, v b je vsota a + b (spodnja 2 bita),
#    z je najvišji bit vsote, c0 se vrne na 0.
#
#    Razred CDKMRippleCarryAdder je v Qiskit 2.x zastarel,
#    zato vezje gradimo ročno iz blokov MAJ in UMA.
# ---------------------------------------------------------------------

def maj(qc, c, b, a):
    """Blok MAJ (majority): v a zapiše prenos MAJ(a, b, c)."""
    qc.cx(a, b)
    qc.cx(a, c)
    qc.ccx(c, b, a)


def uma(qc, c, b, a):
    """Blok UMA (unmajority and add): razveljavi MAJ in v b zapiše vsoto."""
    qc.ccx(c, b, a)
    qc.cx(a, c)
    qc.cx(c, b)


def cuccaro_core():
    qc = QuantumCircuit(6)
    c0, b0, a0, b1, a1, z = 0, 1, 2, 3, 4, 5
    maj(qc, c0, b0, a0)   # prenos iz bita 0 se shrani v a0
    maj(qc, a0, b1, a1)   # prenos iz bita 1 se shrani v a1
    qc.cx(a1, z)          # končni prenos prepišemo v z
    uma(qc, a0, b1, a1)   # obratni vrstni red: popravimo bit 1
    uma(qc, c0, b0, a0)   # popravimo bit 0
    return qc


def cuccaro_inputs():
    inputs = []
    for a in range(4):
        for b in range(4):
            a0, a1 = int_to_bits(a, 2)
            b0, b1 = int_to_bits(b, 2)
            inputs.append([0, b0, a0, b1, a1, 0])
    return inputs


def cuccaro_expected(bits):
    _, b0, a0, b1, a1, _ = bits
    a = bits_to_int([a0, a1])
    b = bits_to_int([b0, b1])
    s0, s1, s2 = int_to_bits(a + b, 3)   # vsota ima največ 3 bite
    return [0, s0, a0, s1, a1, s2]


# ---------------------------------------------------------------------
# Skupni seznam vezij. Druge skripte uporabljajo samo ta slovar
# in funkcije build(), expected(), inputs() spodaj.
# ---------------------------------------------------------------------

CIRCUITS = {
    "toffoli": (toffoli_core, toffoli_inputs, toffoli_expected),
    "fredkin": (fredkin_core, fredkin_inputs, fredkin_expected),
    "polni_sestevalnik": (full_adder_core, full_adder_inputs, full_adder_expected),
    "cuccaro": (cuccaro_core, cuccaro_inputs, cuccaro_expected),
}


def inputs(name):
    """Vrne seznam vseh vhodov za vezje."""
    return CIRCUITS[name][1]()


def build(name, bits):
    """
    Zgradi celotno vezje za en vhod:
    vrata X za pripravo vhoda, barrier, jedro vezja, meritve.

    Barrier prepreči, da bi prevajalnik vrata X zlil z jedrom vezja.
    Tako je jedro po prevajanju enako za vse vhode.
    """
    core = CIRCUITS[name][0]()
    qc = QuantumCircuit(core.num_qubits, name=name)
    for i, b in enumerate(bits):
        if b == 1:
            qc.x(i)
    qc.barrier()
    qc.compose(core, inplace=True)
    qc.measure_all()
    return qc


def expected(name, bits):
    """Pričakovani izhod kot niz v Qiskitovem vrstnem redu."""
    out_bits = CIRCUITS[name][2](bits)
    return to_qiskit_string(out_bits)


# ---------------------------------------------------------------------
# Test: vseh 40 vhodov na idealnem simulatorju mora dati 100 %.
# ---------------------------------------------------------------------

def run_ideal_test(shots=100, seed=1234):
    sim = AerSimulator(seed_simulator=seed)
    n_ok = 0
    n_all = 0
    for name in CIRCUITS:
        for bits in inputs(name):
            qc = transpile(build(name, bits), sim, seed_transpiler=seed)
            counts = sim.run(qc, shots=shots).result().get_counts()
            want = expected(name, bits)
            p = counts.get(want, 0) / shots
            n_all += 1
            if p == 1.0:
                n_ok += 1
            else:
                print(f"NAPAKA {name} vhod={to_qiskit_string(bits)} "
                      f"pričakovano={want} dobljeno={counts}")
    print(f"Pravilnih vhodov: {n_ok}/{n_all}")
    return n_ok == n_all


if __name__ == "__main__":
    ok = run_ideal_test()
    raise SystemExit(0 if ok else 1)
