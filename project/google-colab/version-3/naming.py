"""Output filename compounding for V3 batch runs.

Pure helper (no FaceFusion imports) so it runs on the local machine and on the
remote Colab kernel. Implements the naming rules from project/spec/spec.md:

  target "25-lnka-cc.0756-0838.mp4" + source "ls 65.jpg" + hyperswap_1b_256
    -> "25-lnka-cc.0756-0838 ls65b.mp4"        (first round: space separator)

  target "25-lnka-cc.0756-0838 ls65b.mp4" + source "ls 33.jpg" + hyperswap_1c_256
    -> "25-lnka-cc.0756-0838 ls65b-ls33c.mp4"  (round 2+: hyphen separator)

The trailing letter encodes the face-swapper model (a/b/c/in).
"""

import re
from pathlib import Path

# face-swapper-model -> filename suffix letter(s)
SWAPPER_SUFFIX = {
	'hyperswap_1a_256': 'a',
	'hyperswap_1b_256': 'b',
	'hyperswap_1c_256': 'c',
	'inswapper_128': 'in',
	'inswapper_128_fp16': 'in',
}

# Matches a trailing compound group already appended by a previous round, e.g.
# " ls65b" or " ls65b-ls33c". Used to switch the separator to a hyphen so that
# a second source chains onto the first instead of starting a new group.
_COMPOUND_RE = re.compile(r' [a-z]+\d+[a-z]+(?:-[a-z]+\d+[a-z]+)*$', re.IGNORECASE)


def source_token(source_filename : str) -> str:
	"""'ls 65.jpg' -> 'ls65' (stem with all whitespace removed)."""
	return re.sub(r'\s+', '', Path(source_filename).stem)


def model_suffix(swapper_model : str) -> str:
	if swapper_model not in SWAPPER_SUFFIX:
		raise KeyError(f'unknown face-swapper-model: {swapper_model!r}')
	return SWAPPER_SUFFIX[swapper_model]


def compose_output_name(target_filename : str, source_filename : str, swapper_model : str, ext : str = '.mp4') -> str:
	"""Build the compounded output filename for one (target, source, model) combo."""
	stem = Path(target_filename).stem
	token = source_token(source_filename) + model_suffix(swapper_model)
	separator = '-' if _COMPOUND_RE.search(stem) else ' '
	return f'{stem}{separator}{token}{ext}'
