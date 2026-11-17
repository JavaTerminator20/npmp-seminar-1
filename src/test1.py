from qiskit import QuantumCircuit, transpile

qc = QuantumCircuit(3)
qc.cswap(0, 1, 2)

# polna povezljivost, samo osnovna vrata
t = transpile(qc, basis_gates=["cx", "u"], optimization_level=0)
print(t.count_ops())   # prešteje CNOT
print(t.draw())        # pokaže razgradnjo