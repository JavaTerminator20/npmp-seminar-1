# Raven optimizacije prevajalnika Qiskit in reverzibilna vezja

## Namestitev

Uporabljal sem Python 3.14. Natančne različice paketov so v `requirements.txt`.

Za korake, ki se povežejo na IBM (`--backend ibm_marrakesh`), potrebujete IBM račun.
API ključ se v kodo vnese tako:

```python
from qiskit_ibm_runtime import QiskitRuntimeService
QiskitRuntimeService.save_account(channel="ibm_quantum_platform", token="<VAŠ_KLJUČ>")
```

## Rezultati

Vsi surovi rezultati so že v `results/`. Tabele in grafe iz poročila dobite z:

```
python src/analyze.py
```

## Celoten postopek

Skripte poganjajte iz korena repozitorija, v tem vrstnem redu:

```
# 1. test vezij: vseh 40 vhodov mora na idealnem simulatorju dati 100 %
python src/circuits.py

# 2. strukturne metrike (FakeMarrakesh, postavitve serije B z ibm_marrakesh)
python src/transpile_run.py --layouts-B results/simulate/layouts_B_ibm_marrakesh.json

# 3. idealni in šumni simulator (šumni model iz kalibracije ibm_marrakesh)
python src/simulate.py --backend ibm_marrakesh

# 4. pravi procesor (porabi kvoto, pred oddajo vpraša za potrditev)
python src/hardware.py poskus --backend ibm_marrakesh
python src/hardware.py A --backend ibm_marrakesh
python src/hardware.py B --backend ibm_marrakesh

# 5. kalibracije procesorja (takoj po koraku 4)
python src/save_calibration.py

# 6. tabele in grafi
python src/analyze.py
```
Datoteka `results/simulate/layouts_B_ibm_marrakesh.json` (korak 2) je v repozitoriju.
Če začnete brez nje, najprej poženite korak 3, ki jo ustvari.

Brez IBM računa lahko korak 3 poženete s `--backend fake_marrakesh`,
korak 4 pa preizkusite lokalno s `python src/hardware.py A --backend fake_marrakesh`.

Koraki 3–5 prepišejo shranjene rezultate. Če jih želite le primerjati, podajte `--out-dir <mapa>`
(pri `simulate.py` in `hardware.py`).

## Kaj se ponovi natančno

- **Koraka 1 in 2** dasta enake številke, ker so semena prevajalnika fiksna (`seed_transpiler` 0–9).
  Razlikuje se le čas prevajanja, ki je odvisen od računalnika.
- **Korak 3** uporabi seme simulatorja 12345, a šumni model zgradi iz *trenutne* kalibracije
  `ibm_marrakesh`. Moji rezultati so iz kalibracije 19. 11. 2026 (glej `results/simulate/noisy_meta.json`),
  zato bodo nove številke nekoliko drugačne.
- **Korak 4** se ne da ponoviti natančno, saj se procesor stalno spreminja. ID-ji mojih nalog so
  v `results/hardware/ibm_jobs.csv`.
- **Korak 6** iz datotek v `results/` vedno da enake tabele in grafe kot v poročilu.

