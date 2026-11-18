# Kaj ni delovalo

## 18. 11. 2026 – zastarel razred za Cuccarov seštevalnik
- Načrt je predvidel `CDKMRippleCarryAdder(2)` iz `qiskit.circuit.library`.
- V Qiskit 2.6.2 ob uporabi dobimo `DeprecationWarning`: razred je zastarel
  od Qiskit 2.1 in bo odstranjen v Qiskit 3.0. Predlagana zamenjava so vrata
  `HalfAdderGate` / `FullAdderGate`, ki pa ne določajo konkretne gradnje vezja.
- Rešitev: 2-bitni Cuccarov seštevalnik smo zgradili ročno iz blokov MAJ in UMA
  (`src/circuits.py`, funkcija `cuccaro_core`). Test na idealnem simulatorju
  je uspel na vseh 16 vhodih.

## 18. 11. 2026 – vhodi z vodilnimi ničlami v CSV
- Pri dopisovanju v `hardware.csv` je pandas ponovno prebral obstoječo datoteko
  in vhod `"000"` pretvoril v število `0` (enako `pricakovano`).
- Rešitev: obstoječo datoteko beremo z `pd.read_csv(..., dtype=str)`.
  Tudi `analyze.py` mora stolpca `vhod` in `pricakovano` brati kot niz.
