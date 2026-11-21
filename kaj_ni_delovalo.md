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

## 21. 11. 2026 – različne postavitve serije B v strukturnih metrikah in zagonih
- `transpile_run.py` je postavitve serije B izbral iz kalibracije `FakeMarrakesh`
  (npr. kubiti 12, 13, 14 za Toffolija), `simulate.py` in `hardware.py` pa iz kalibracije
  `ibm_marrakesh` 19. 11. 2026 ob 8.37 (kubiti 20, 21, 22).
- Število dvokubitnih vrat v `structural.csv` se je zato v seriji B pri 63 od 160
  kombinacij razlikovalo od vezij, ki so tekla na šumnem modelu in procesorju.
  Serija A je bila pravilna (enaka v vseh 160 kombinacijah).
- Rešitev: `transpile_run.py` ima možnost `--layouts-B`, ki prebere postavitve iz datoteke.
  Ponoven zagon z `results/simulate/layouts_B_ibm_marrakesh.json` da v obeh serijah
  enako število dvokubitnih vrat kot vezja, pognana na `ibm_marrakesh`.

## 21. 11. 2026 – povprečje sprememb čez vezja
- `analyze.py` je povprečno spremembo števila vrat (vrstica "povprecje" v tabeli 3)
  računal kot povprečje odstotkov posameznih vezij (28,6 %).
- V Metodah je določeno, da najprej povprečimo števila vrat, nato izračunamo spremembo
  (26,8 %). Kodo smo popravili, da sledi Metodam. Pri P_pravilno je rezultat enak.
