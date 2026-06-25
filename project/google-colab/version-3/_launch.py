"""Detached launcher run via `colab exec -f`. Starts v3_batch_run.py as a
background process on the VM and returns immediately, so the local orchestrator
never has to hold a live connection for the whole (multi-minute) batch. Progress
goes to /content/batch.log; completion is signalled by a marker in the bucket.
"""

import subprocess
import sys

subprocess.Popen(
	[sys.executable, '/content/v3_batch_run.py'],
	stdout=open('/content/batch.log', 'a'),
	stderr=subprocess.STDOUT,
	start_new_session=True,
)
print('LAUNCHED /content/v3_batch_run.py (detached) — progress in /content/batch.log')
