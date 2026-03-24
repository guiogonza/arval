"""
Fuerza bruta para desbloquear PDF protegido.
Enfoque: contraseñas numéricas (NIT, cédula, etc.)
"""
import pikepdf
import sys
import time
import itertools

PDF_INPUT  = r"C:\Users\guiog\OneDrive\Documentos\RUT T-KARGA 2026.pdf"
PDF_OUTPUT = r"C:\Users\guiog\OneDrive\Documentos\RUT T-KARGA 2026 (sin clave).pdf"

def try_pw(pw):
    try:
        pdf = pikepdf.open(PDF_INPUT, password=pw)
        pdf.save(PDF_OUTPUT)
        return True
    except pikepdf.PasswordError:
        return False

# ── FASE 1: Variaciones inteligentes del NIT que ya probaste ──
nit_base = "9004968532"
smart_guesses = set()

# Variaciones del NIT
for i in range(len(nit_base)):
    smart_guesses.add(nit_base[:i])       # prefijos
    smart_guesses.add(nit_base[i:])       # sufijos
smart_guesses.add(nit_base)
smart_guesses.add(nit_base[:-1])          # sin dígito verificación
smart_guesses.add(nit_base[:-2])

# Con guiones/puntos
for sep in ["-", ".", " "]:
    smart_guesses.add(f"900{sep}496{sep}853{sep}2")
    smart_guesses.add(f"900{sep}496{sep}853")
    smart_guesses.add(f"900496853{sep}2")

# Passwords comunes DIAN
smart_guesses.update([
    "tkarga", "TKARGA", "T-KARGA", "t-karga", "Tkarga",
    "tkarga2026", "TKARGA2026", "tkarga2025", "TKARGA2025",
    "colombia", "Colombia", "COLOMBIA",
    "password", "Password", "abc123", "admin",
    "rut", "RUT", "Rut", "dian", "DIAN", "Dian",
    "rut2026", "RUT2026", "rut2025", "RUT2025",
])

# Descartar vacíos
smart_guesses.discard("")

print(f"=== DESBLOQUEANDO: {PDF_INPUT} ===\n")
print(f"FASE 1: {len(smart_guesses)} variaciones inteligentes...")

for pw in sorted(smart_guesses):
    if try_pw(pw):
        print(f"\n>>> EXITO! Contraseña: '{pw}'")
        print(f">>> Guardado en: {PDF_OUTPUT}")
        sys.exit(0)

print("  No encontrada en fase 1.\n")

# ── FASE 2: Todos los números de 1 a 7 dígitos (0-9999999) ──
print("FASE 2: Números de 1 a 7 dígitos (0 - 9,999,999)...")
start = time.time()
count = 0
for n in range(0, 10_000_000):
    pw = str(n)
    count += 1
    if count % 50000 == 0:
        elapsed = time.time() - start
        rate = count / elapsed if elapsed > 0 else 0
        print(f"  Probando: {pw:>8s} | {count:,} intentos | {rate:.0f}/s")
    if try_pw(pw):
        print(f"\n>>> EXITO! Contraseña: '{pw}'")
        print(f">>> Guardado en: {PDF_OUTPUT}")
        sys.exit(0)

print("  No encontrada en fase 2.\n")

# ── FASE 3: Números de 8 a 10 dígitos empezando por rangos de NIT/CC ──
# NITs colombianos: 800000000-999999999, Cédulas: 1000000-99999999+
ranges = [
    (800_000_000, 999_999_999, "NITs 800M-999M"),
    (10_000_000, 99_999_999, "Cédulas 8 dígitos"),
    (1_000_000_000, 1_200_000_000, "Cédulas 10 dígitos"),
]

for lo, hi, desc in ranges:
    print(f"FASE 3: {desc} ({lo:,} - {hi:,})...")
    start = time.time()
    count = 0
    for n in range(lo, hi + 1):
        pw = str(n)
        count += 1
        if count % 200000 == 0:
            elapsed = time.time() - start
            rate = count / elapsed if elapsed > 0 else 0
            pct = count / (hi - lo + 1) * 100
            print(f"  {pw} | {pct:.1f}% | {rate:.0f}/s")
        if try_pw(pw):
            print(f"\n>>> EXITO! Contraseña: '{pw}'")
            print(f">>> Guardado en: {PDF_OUTPUT}")
            sys.exit(0)
    print(f"  Rango {desc} completado sin éxito.\n")

print("No se pudo encontrar la contraseña.")
print("Opciones: instalar 'pdfcrack' o 'hashcat' para fuerza bruta más rápida.")
