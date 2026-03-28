import subprocess
import sys

print(f"Using Python: {sys.executable}")
print("Installing setuptools (provides distutils)...")
subprocess.run([sys.executable, "-m", "pip", "install", "setuptools", "-q"], check=True)
print("✓ setuptools installed")
