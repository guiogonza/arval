"""
Script para eliminar contraseña de un PDF.
Intenta:
1. Abrir sin contraseña (quita restricciones de permisos)
2. Probar contraseñas comunes si requiere contraseña de apertura
"""
import pikepdf
import sys

PDF_INPUT = r"C:\Users\guiog\OneDrive\Documentos\RUT T-KARGA 2026.pdf"
PDF_OUTPUT = r"C:\Users\guiog\OneDrive\Documentos\RUT T-KARGA 2026 (sin clave).pdf"

# Contraseñas comunes a probar
passwords_to_try = [
    "",  # vacía
    # NIT / cédula patterns comunes para RUT
    "tkarga", "TKARGA", "T-KARGA", "t-karga",
    "2026", "2025", "2024", "2023",
    "1234", "12345", "123456", "1234567890",
    "0000", "0001",
    # Combinaciones típicas RUT DIAN
    "rut", "RUT", "rut2026", "RUT2026",
]

def try_open(password=None):
    """Intenta abrir el PDF con la contraseña dada."""
    kwargs = {}
    if password is not None:
        kwargs["password"] = password
    return pikepdf.open(PDF_INPUT, **kwargs)

# Intento 1: sin contraseña (solo restricciones de permisos)
print(f"Archivo: {PDF_INPUT}")
print("=" * 50)

try:
    pdf = try_open()
    pdf.save(PDF_OUTPUT)
    print("El PDF solo tenía restricciones de permisos (no de apertura).")
    print(f"Guardado sin protección en:\n  {PDF_OUTPUT}")
    sys.exit(0)
except pikepdf.PasswordError:
    print("El PDF requiere contraseña de apertura. Probando contraseñas...")

# Intento 2: probar lista de contraseñas
for pw in passwords_to_try:
    try:
        pdf = try_open(pw)
        pdf.save(PDF_OUTPUT)
        print(f"\nContraseña encontrada: '{pw}'")
        print(f"Guardado sin protección en:\n  {PDF_OUTPUT}")
        sys.exit(0)
    except pikepdf.PasswordError:
        continue

# Si ninguna funcionó, pedir al usuario
print("\nNinguna contraseña común funcionó.")
print("Ingresa contraseñas manualmente (escribe 'salir' para terminar):\n")
while True:
    pw = input("Contraseña a probar: ").strip()
    if pw.lower() == "salir":
        break
    try:
        pdf = try_open(pw)
        pdf.save(PDF_OUTPUT)
        print(f"\nContraseña correcta: '{pw}'")
        print(f"Guardado sin protección en:\n  {PDF_OUTPUT}")
        sys.exit(0)
    except pikepdf.PasswordError:
        print("  Incorrecta, intenta otra.")

print("\nNo se pudo desbloquear el PDF.")
