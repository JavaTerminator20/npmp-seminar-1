# Tabela 2: verjetnost pravilnega rezultata P_pravilno [%]

Šumni model: povprečje čez 10 semen. Procesor: eno seme. A0 = serija A, raven 0.

| Vezje | Platforma | A0 | A1 | A2 | A3 | B0 | B1 | B2 | B3 |
| :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| Toffoli | idealni simulator | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Toffoli | šumni model | 94.2 | 95.4 | 95.8 | 96.0 | 94.1 | 94.3 | 95.0 | 95.0 |
| Toffoli | šumni model (seme kot na procesorju) | 94.1 | 95.3 | 95.9 | 96.1 | 94.0 | 94.2 | 95.2 | 95.2 |
| Toffoli | procesor | 81.0 | 93.3 | 93.3 | 94.6 | 91.0 | 91.5 | 92.4 | 91.6 |
| Fredkin | idealni simulator | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Fredkin | šumni model | 93.6 | 95.0 | 95.2 | 95.3 | 93.4 | 94.0 | 94.6 | 94.6 |
| Fredkin | šumni model (seme kot na procesorju) | 93.9 | 95.0 | 95.2 | 95.3 | 93.7 | 94.0 | 94.6 | 94.6 |
| Fredkin | procesor | 79.7 | 92.7 | 92.7 | 94.4 | 91.3 | 91.7 | 91.7 | 91.9 |
| Polni seštevalnik | idealni simulator | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Polni seštevalnik | šumni model | 89.8 | 90.9 | 91.1 | 93.6 | 89.2 | 90.5 | 91.0 | 91.0 |
| Polni seštevalnik | šumni model (seme kot na procesorju) | 90.4 | 90.9 | 91.1 | 93.7 | 89.5 | 90.5 | 91.0 | 91.0 |
| Polni seštevalnik | procesor | 73.4 | 89.3 | 89.6 | 85.6 | 75.6 | 77.3 | 78.8 | 78.0 |
| Cuccaro | idealni simulator | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Cuccaro | šumni model | 78.1 | 81.5 | 82.4 | 83.9 | 74.4 | 77.2 | 79.2 | 79.2 |
| Cuccaro | šumni model (seme kot na procesorju) | 78.6 | 81.7 | 83.2 | 83.5 | 74.8 | 77.2 | 79.2 | 79.2 |
| Cuccaro | procesor | 56.6 | 60.4 | 62.4 | 61.7 | 26.1 | 29.6 | 30.2 | 30.6 |

Opomba: »šumni model« je povprečje čez 10 semen prevajalnika (0–9). »šumni model (seme kot na procesorju)« ni povprečje, ampak samo eno seme prevajalnika, isto kot je bilo uporabljeno na pravem procesorju IBM. Šumni model je v obeh vrsticah isti.
