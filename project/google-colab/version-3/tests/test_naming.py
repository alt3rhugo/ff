"""Unit tests for naming.compose_output_name — covers all spec.md examples."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from naming import compose_output_name, source_token, model_suffix  # noqa: E402


def test_source_token_strips_whitespace():
	assert source_token('ls 65.jpg') == 'ls65'
	assert source_token('ls 33.png') == 'ls33'
	assert source_token('nospace.jpg') == 'nospace'


def test_first_round_uses_space_separator():
	out = compose_output_name('25-lnka-cc.0756-0838.mp4', 'ls 65.jpg', 'hyperswap_1b_256')
	assert out == '25-lnka-cc.0756-0838 ls65b.mp4'


def test_first_round_other_target():
	out = compose_output_name('20-lnka-cc.0644-0725.mp4', 'ls 65.jpg', 'hyperswap_1b_256')
	assert out == '20-lnka-cc.0644-0725 ls65b.mp4'


def test_round_two_uses_hyphen_separator():
	# target is itself a round-1 output, new source ls 33 with model 1c
	out = compose_output_name('25-lnka-cc.0756-0838 ls65b.mp4', 'ls 33.jpg', 'hyperswap_1c_256')
	assert out == '25-lnka-cc.0756-0838 ls65b-ls33c.mp4'


def test_round_two_with_b_model():
	out = compose_output_name('25-lnka-cc.0756-0838 ls65b.mp4', 'ls 33.jpg', 'hyperswap_1b_256')
	assert out == '25-lnka-cc.0756-0838 ls65b-ls33b.mp4'


@pytest.mark.parametrize('model, suffix', [
	('hyperswap_1a_256', 'a'),
	('hyperswap_1b_256', 'b'),
	('hyperswap_1c_256', 'c'),
	('inswapper_128', 'in'),
	('inswapper_128_fp16', 'in'),
])
def test_all_model_suffixes(model, suffix):
	assert model_suffix(model) == suffix
	out = compose_output_name('25-lnka-cc.0756-0838.mp4', 'ls 65.jpg', model)
	assert out == f'25-lnka-cc.0756-0838 ls65{suffix}.mp4'


def test_inswapper_round_two():
	out = compose_output_name('25-lnka-cc.0756-0838 ls65in.mp4', 'ls 33.jpg', 'inswapper_128_fp16')
	assert out == '25-lnka-cc.0756-0838 ls65in-ls33in.mp4'


def test_unknown_model_raises():
	with pytest.raises(KeyError):
		compose_output_name('a.mp4', 'b.jpg', 'totally_unknown_model')
