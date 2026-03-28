import subprocess
import sys

packages = ["undetected-chromedriver", "selenium"]

for pkg in packages:
    print(f"Installing {pkg}...")
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=True)
    print(f"✓ {pkg} installed")

print("\nAll dependencies installed!")
