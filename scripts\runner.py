import subprocess
import sys

result = subprocess.run([sys.executable, "run.py"], capture_output=False)
sys.exit(result.returncode)
