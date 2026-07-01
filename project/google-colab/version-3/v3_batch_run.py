"""FFusion V3 — remote batch runner (executed on a Colab GPU via `colab exec -f`).

Mirrors version-2/dagshub.py but processes a whole batch:

  1. clone the fork + install dependencies (skipped if already present)
  2. read /content/batch_config.json (token, repo, DagsHub prefixes)
  3. pull every source/target + override.ini from the DagsHub storage bucket (S3)
  4. read the face-swapper-model from override.ini -> filename suffix letter
  5. for each (target x source) run facefusion.py headless-run with --config-path
  6. upload each result back to the DagsHub bucket under the output prefix (S3)

Runs as plain Python (subprocess, not IPython `!` magics) so it behaves the same
whether `colab exec` sends it to an IPython kernel or a bare interpreter. Inputs
and outputs both move over the DagsHub S3 bucket (the same endpoint V2 used for
upload), so no rclone/fuse3/dagshub mount is needed on the VM.

`naming.py` must sit next to this file on the remote VM (orchestrate.py uploads
both). The DagsHub token lives only in batch_config.json on the ephemeral VM and
is never written to the repo.
"""

import configparser
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
	_HERE = Path(__file__).resolve().parent
except NameError:  # `colab exec -f` runs the file content as a kernel cell — no __file__
	_HERE = Path('/content')
sys.path.insert(0, str(_HERE))
from naming import compose_output_name  # noqa: E402

FORK_URL = 'https://github.com/alt3rhugo/ff.git'
FF_DIR = Path('/content/facefusion')
CONFIG_PATH = Path('/content/batch_config.json')
INPUT_DIR = Path('/content/batch')
OUTPUT_DIR = Path('/content/output')
DEFAULT_SWAPPER_MODEL = 'hyperswap_1b_256'

VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.webm', '.avi'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}


def run(cmd, **kwargs):
	print(f'+ {" ".join(str(c) for c in cmd)}', flush=True)
	subprocess.run(cmd, check=True, **kwargs)


def ensure_boto3():
	# Installed first (before the slow clone/install) so the status markers can
	# always be written, even if FaceFusion setup itself fails.
	run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'])


def setup_facefusion():
	if FF_DIR.exists():
		print(f'✓ {FF_DIR} already present — skipping clone/install', flush=True)
		return
	run(['git', 'clone', FORK_URL, str(FF_DIR)])
	run([sys.executable, 'install.py', '--onnxruntime', 'cuda', '--skip-conda'], cwd=FF_DIR)


def load_config():
	cfg = json.loads(CONFIG_PATH.read_text())
	os.environ['DAGSHUB_USER_TOKEN'] = cfg['dagshub_token']
	return cfg


def s3_client(cfg):
	import boto3

	return boto3.client(
		's3',
		endpoint_url=f"https://dagshub.com/api/v1/repo-buckets/s3/{cfg['repo_owner']}",
		aws_access_key_id=cfg['dagshub_token'],
		aws_secret_access_key=cfg['dagshub_token'],
	)


def _download_prefix(s3, bucket, prefix, dest_dir, exts):
	"""Download every object directly under `prefix/` into dest_dir; return paths."""
	dest_dir.mkdir(parents=True, exist_ok=True)
	paths = []
	resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
	for obj in resp.get('Contents', []):
		key = obj['Key']
		name = key[len(prefix):].lstrip('/')
		if not name or '/' in name:  # skip the folder marker / nested files
			continue
		if Path(name).suffix.lower() not in exts:
			continue
		local = dest_dir / name
		s3.download_file(bucket, key, str(local))
		paths.append(local)
	return sorted(paths)


def pull_inputs(s3, cfg):
	bucket = cfg['repo_name']
	prefix = cfg['input_prefix'].strip('/')  # e.g. "batch"
	sources = _download_prefix(s3, bucket, f'{prefix}/sources/', INPUT_DIR / 'sources', IMAGE_EXTS)
	targets = _download_prefix(s3, bucket, f'{prefix}/targets/', INPUT_DIR / 'targets', VIDEO_EXTS)
	override = INPUT_DIR / 'override.ini'
	s3.download_file(bucket, f'{prefix}/override.ini', str(override))
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	print(f'✓ {len(sources)} source(s), {len(targets)} target(s)', flush=True)
	return sources, targets, override


def read_swapper_model(override_ini):
	parser = configparser.ConfigParser()
	parser.read(override_ini)
	model = parser.get('processors', 'face_swapper_model', fallback='').strip()
	return model or DEFAULT_SWAPPER_MODEL


def glob_safe_target(target):
	"""FaceFusion names its temp frame dir after the target stem and then
	globs it (temp_helper.get_temp_directory_path + resolve_file_pattern). A stem
	containing glob metacharacters ([ ] * ?) — e.g. "10 [ai] wine ...mp4" — makes
	glob treat "[ai]" as a character class, so the frames are never found and the
	run dies with "temporary frames not found". Point -t at a metachar-free symlink
	(copy fallback) so the temp dir name is glob-safe; the real name is preserved on
	the -o output, which is written directly (never globbed)."""
	if not re.search(r'[\[\]\*\?]', target.stem):
		return target
	safe_dir = INPUT_DIR / '_safe_targets'
	safe_dir.mkdir(parents=True, exist_ok=True)
	safe = safe_dir / (re.sub(r'[\[\]\*\?]', '_', target.stem) + target.suffix)
	if not safe.exists():
		try:
			os.symlink(target, safe)
		except (OSError, NotImplementedError):
			import shutil
			shutil.copy2(target, safe)
	return safe


def process(sources, targets, override_ini, swapper_model):
	results = []
	for target in targets:
		safe_target = glob_safe_target(target)
		for source in sources:
			out_name = compose_output_name(target.name, source.name, swapper_model)
			out_path = OUTPUT_DIR / out_name
			print(f'\n=== {target.name}  x  {source.name}  ->  {out_name} ===', flush=True)
			cmd = [
				sys.executable, 'facefusion.py', 'headless-run',
				'--execution-providers', 'cuda',
				'--config-path', str(override_ini),
				'-s', str(source),
				'-t', str(safe_target),
				'-o', str(out_path),
			]
			print(f'+ {" ".join(str(c) for c in cmd)}', flush=True)
			# Capture combined output so the failure marker can carry FaceFusion's
			# real stderr (the detached batch.log dies with the session).
			proc = subprocess.run(cmd, cwd=FF_DIR, text=True,
								   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			print(proc.stdout, flush=True)
			if proc.returncode != 0:
				tail = '\n'.join((proc.stdout or '').splitlines()[-40:])
				raise RuntimeError(
					f'headless-run exit {proc.returncode} for {out_name}\n{tail}')
			if not out_path.exists():
				raise RuntimeError(f'headless run produced no output at {out_path}')
			results.append(out_path)
	return results


def upload_outputs(s3, cfg, results):
	from boto3.s3.transfer import TransferConfig

	# DagsHub's S3 endpoint returns 500 on CreateMultipartUpload; force a single
	# PUT by lifting the multipart threshold above any plausible video size (5 GB).
	single_part = TransferConfig(multipart_threshold=5 * 1024 ** 3)
	output_prefix = cfg['output_prefix'].strip('/')  # e.g. "batch/output"
	for path in results:
		key = f'{output_prefix}/{path.name}'
		s3.upload_file(str(path), cfg['repo_name'], key, Config=single_part)
		print(f'✓ uploaded -> s3://{cfg["repo_name"]}/{key}', flush=True)


def write_marker(s3, cfg, name, data):
	"""Write a small JSON status marker to the output prefix so the local
	orchestrator can detect completion by polling the bucket (no live connection)."""
	key = f"{cfg['output_prefix'].strip('/')}/{name}"
	s3.put_object(Bucket=cfg['repo_name'], Key=key, Body=json.dumps(data).encode())
	print(f'✓ marker -> s3://{cfg["repo_name"]}/{key}', flush=True)


def main():
	ensure_boto3()
	cfg = load_config()
	s3 = s3_client(cfg)
	try:
		setup_facefusion()
		sources, targets, override_ini = pull_inputs(s3, cfg)
		if not sources or not targets:
			raise SystemExit('no sources or targets found — nothing to process')
		swapper_model = read_swapper_model(override_ini)
		print(f'face-swapper-model: {swapper_model}', flush=True)
		results = process(sources, targets, override_ini, swapper_model)
		upload_outputs(s3, cfg, results)
		write_marker(s3, cfg, '_SUCCESS.json', {
			'outputs': [p.name for p in results],
			'model': swapper_model,
		})
		print(f'\n✓ batch complete — {len(results)} output(s) uploaded', flush=True)
	except BaseException as error:  # noqa: B036 - record any failure for the poller
		import traceback
		write_marker(s3, cfg, '_FAILED.json', {'error': f'{type(error).__name__}: {error}'})
		traceback.print_exc()
		raise


if __name__ == '__main__':
	main()
