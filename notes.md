# Za zapomnit

- **algoritem Sabre**, ki se uporablja za izbiro postavitve, deluje nakljucno, odvisno od semena - zato je treba veckrat pognati z razlicnim semenom in povpreciti na koncu.
- **metrika za dolocanje fizicnih qubitov**: IBM procesor redno kalibrira. Za vsak par sosednjih kubitov izmeri, kako pogosto dvokubitna vrata cz na tem paru dajo napačen rezultat. To je napaka vrat, na primer 0.003. Pomeni približno 0,3 % možnosti, da gre pri enih vratih na tem paru kaj narobe. Podobno ima vsak kubit napako meritve, na primer 0.02: v 2 % primerov preberemo napačen bit. Vrednosti se med pari zelo razlikujejo. Nekateri pari so dobri, drugi so lahko desetkrat slabši. Tvoje vezje se bo izvajalo na izbranih kubitih in njihovih povezavah. Čim manjše so te napake, tem večja bo P_pravilno.
- **barrier:** ki se uporablja v `build()` -- s tem povemo da prevajalnik ne bo optimiziral cel to crto - zato da ne bo optimiziral zacetnih `X` vrat ki se uporabljajo da nastavimo zacetni qubit na logicno vredonst `1`
- **kalibracija:** Kubiti na pravem kvantnem procesorju niso popolni in tudi niso vsi enako dobri. IBM zato vsak procesor redno, približno enkrat na dan, izmeri. Temu pravijo kalibracija. Za vsak kubit in vsak par kubitov izmerijo:
    - T1: Koliko časa kubit ostane v stanju 1, preden sam pade v 0 (»izgubi energijo«).
    - T2: Koliko časa kubit ohrani superpozicijo oziroma fazo.
    - Napaka enokubitnih vrat: Verjetnost, da npr. vrata X ali SX naredijo napako (zelo majhna, ~0,0002).
    - Napaka dvokubitnih vrat: #nako za vrata CZ med dvema sosednjima kubitoma (precej večja, vrat ~0,003–0,01).
    - Napaka meritve: Verjetnost, da izmeriš 1, čeprav je bil kubit v 0, ali obratno (~1–3%).
    - Trajanje vrat: koliko nanosekund trajajo posamezna vrata.

    Te številke se sčasoma spreminjajo (temperatura, motnje, ponovna nastavitev naprave). Kubit, ki je bil včeraj dober, je lahko danes slab. Zato ima vsaka kalibracija svoj datum.

    Kje to nastopi v simulate.py

    1. Šumni model (simulate.py:194)
    noisy_sim = AerSimulator.from_backend(backend, ...)
    from_backend prebere zgornje številke in iz njih zgradi šumni model. Simulator med simulacijo nato naključno vstavlja napake s temi verjetnostmi. Tako se »obnaša« kot pravi procesor.

    2. Od kod pridejo številke
    - `--backend fake_torino` (privzeto): FakeTorino je shranjen posnetek ene stare kalibracije pravega procesorja ibm_torino, ki je priložen paketu qiskit-ibm-runtime. Ne potrebuje interneta ali računa. Številke pa niso današnje.
    - `--backend ibm_torino`: skripta prenese današnjo kalibracijo pravega procesorja. To ne porabi kvote časa procesorja, saj samo prebere podatke in ne požene nobenega vezja.

    3. Datum kalibracije (simulate.py:70, calibration_date)
    Samo prebere, kdaj je bila kalibracija izmerjena, in ga zapiše v noisy_meta.json. Tako veš, iz katerega dne je šumni model.

    4. Postavitve za serijo B (load_layouts_B)
    Pri seriji B izberemo povezane fizične kubite z najmanjšimi napakami. »Najmanjše napake« pomeni ravno po podatkih iz kalibracije. Zato so postavitve shranjene skupaj z imenom procesorja in datumom kalibracije.

    Zakaj je to pomembno za tvojo nalogo

    Rezultate šumnega simulatorja primerjaš z rezultati pravega procesorja. Ta primerjava je poštena samo, če šumni model opisuje procesor takšen, kot je bil na dan zagona. Zato komentar na začetku datoteke priporoča tak vrstni red:

    1. Na dan, ko poženeš hardware.py, poženi tudi python src/simulate.py --backend ibm_torino.
    2. Tako sta šumni model in pravi zagon iz iste kalibracije.

    Če bi uporabil FakeTorino (stara kalibracija), bi bila razlika med simulatorjem in procesorjem deloma posledica tega, da se je procesor medtem spremenil, in ne samo tega, da je šumni model poenostavljen.

- Serija A in serija B se razlikujeta samo v tem, kdo izbere postavitev (layout), torej na katere fizične kubite procesorja se preslikajo logični kubiti.

    1. Serija A: privzeto prevajanje
    - Prevajalnik pri vsaki ravni optimizacije in vsakem semenu postavitev izbere sam.
    - Ta izbira se med ravnmi razlikuje. Razlika v P_pravilno med ravnmi je zato skupni učinek dveh stvari: optimizacije vrat in različne postavitve.

    2.Serija B: fiksna postavitev
    - Za vsako vezje enkrat izberemo skupino povezanih fizičnih kubitov z majhnimi napakami (choose_layout_B v src/transpile_run.py:82). Izbira je požrešna: išče najmanjšo vsoto napak dvokubitnih vrat in napak meritve.
    - To postavitev dobijo vse ravni 0–3 kot initial_layout. Shranjena je v results/transpile_run/layouts_B.json, isto datoteko uporablja tudi simulate.py.
    - Ker so fizični kubiti pri vseh ravneh enaki, razlika med ravnmi pokaže samo učinek optimizacije.

    Zakaj primerjava: ko seriji primerjamo (graf 4), ločimo, koliko k pravilnosti prispeva izbira postavitve in koliko optimizacija vezja.

- **strukturne metrike:** iz `transpile_run.py` so iz `FakeMarrakesh` ne iz pravega - to omeni v *Metode* v porocilu.
