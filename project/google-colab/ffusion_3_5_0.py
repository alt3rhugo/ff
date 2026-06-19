# -*- coding: utf-8 -*-
"""FFusion 3.5.0 — Version 1 (Gradio, manual upload)

Self-contained flow against the user's own FaceFusion fork.
All custom changes (Gradio public link, NSFW off, hash guard off) are already
baked into the fork, so there is NO runtime patching here.

Run on a Colab GPU runtime (Runtime -> Change runtime type -> GPU).
"""

# === CELL 1: CLONE THE FORK ===
import os

# %cd /content
get_ipython().system('rm -rf facefusion')
get_ipython().system('git clone https://github.com/alt3rhugo/ff.git facefusion')
# %cd facefusion

# === CELL 2: INSTALL DEPENDENCIES (latest, via the repo's own installer) ===
# install.py reads requirements.txt and swaps in onnxruntime-gpu==1.24.4 for cuda.
# --skip-conda bypasses the conda check (Colab has no conda).
get_ipython().system('python install.py --onnxruntime cuda --skip-conda')

# === CELL 3: LAUNCH GRADIO (public link; upload target + source in the UI) ===
# share=True is baked into the fork's layout files, so a public URL is printed.
get_ipython().system('mkdir -p /content/output')
get_ipython().system('python facefusion.py run --execution-providers cuda --output-path /content/output')
