## Kje so rezultati

Vsaka skripta piše v svojo podmapo `results/<ime skripte>/`:

| Skripta | Mapa | Datoteke |
|---|---|---|
| `src/transpile_run.py` | `results/transpile_run/` | `structural.csv`, `layouts_B.json`, `passes.txt`, `passes_diff.txt` |
| `src/simulate.py` | `results/simulate/` | `ideal.csv`, `noisy.csv`, `noisy_counts.json`, `noisy_meta.json`, `layouts_B_<procesor>.json` |
| `src/hardware.py` | `results/hardware/` | `hardware.csv`, `ibm_jobs.csv`, `jobs.json`, `jobs/` (preizkus s `fake_...` v `results/hardware/preizkus/`) |
| `src/save_calibration.py` | `results/hardware/` | `kalibracija.json` (kalibracije procesorja, uporabljene pri poskusih; poženite takoj po `hardware.py`) |
| `src/analyze.py` | `results/analyze/` | `tabela1–3_*.csv` in `.md` (grafi gredo v `figures/`) |

Strukturne metrike v poročilu so izračunane za `FakeMarrakesh` s postavitvami serije B,
ki sta jih na `ibm_marrakesh` uporabila `simulate.py` in `hardware.py`:

```
python src/transpile_run.py --layouts-B results/simulate/layouts_B_ibm_marrakesh.json
python src/analyze.py
```

