"""FFusion V3 — local orchestrator (runs on your machine, no human in the loop).

Drives a full batch end to end via the Google Colab CLI + DagsHub storage:

  1. upload local sources/ + targets/ + override.ini to the DagsHub bucket
  2. start a Colab GPU session, upload the run scripts, and launch the batch
     DETACHED (a short `colab exec` that returns in seconds)
  3. poll the bucket for a _SUCCESS/_FAILED marker the remote writes when done
  4. download the results from the bucket into --out
  5. stop the Colab session (best effort, always)

Why detached + poll: holding a live `colab exec` connection for the whole
multi-minute job is fragile — a brief local network blip kills it and can strand
the GPU session. Polling the bucket makes each network call independent and
retryable, and the persistent poller keeps the VM's keep-alive daemon alive.

Prerequisites:
  * Colab CLI installed + authenticated:  uv tool install google-colab-cli
  * DAGSHUB_USER_TOKEN available locally (env var or a .env file beside this script)
  * pip install boto3

Input folder layout (--inputs):
    sources/   ls 65.jpg, ls 33.jpg, ...
    targets/   25-lnka-cc.0756-0838.mp4, ...
    override.ini

Usage:
    python orchestrate.py --inputs ./batch_in --out ./batch_out
    python orchestrate.py --inputs ./batch_in --dry-run        # print the matrix only
    python orchestrate.py --stop                               # reclaim a stranded session
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from naming import compose_output_name  # noqa: E402

# Windows consoles default to a non-UTF-8 codepage (e.g. cp1250); force UTF-8 so
# the checkmarks in our output and in the streamed remote logs don't crash on
# encode. Setting the env var makes child `colab` processes inherit it too.
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
for _stream in (sys.stdout, sys.stderr):
	try:
		_stream.reconfigure(encoding='utf-8')
	except (AttributeError, ValueError):
		pass

HERE = Path(__file__).resolve().parent
REPO_OWNER = 'zbynja'
REPO_NAME = 'ff'
INPUT_PREFIX = 'batch'
OUTPUT_PREFIX = 'batch/output'
DEFAULT_SWAPPER_MODEL = 'hyperswap_1b_256'
SUCCESS_MARKER = '_SUCCESS.json'
FAILED_MARKER = '_FAILED.json'
POLL_INTERVAL = 15        # seconds between bucket polls
POLL_TIMEOUT = 60 * 60    # give up after an hour

VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.webm', '.avi'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}


# ---------------------------------------------------------------- helpers

def load_token():
	token = os.environ.get('DAGSHUB_USER_TOKEN')
	if not token:
		env_file = HERE / '.env'
		if env_file.exists():
			for line in env_file.read_text().splitlines():
				if line.strip().startswith('DAGSHUB_USER_TOKEN'):
					token = line.split('=', 1)[1].strip().strip('"\'')
	if not token:
		sys.exit('DAGSHUB_USER_TOKEN not set (env var or .env beside orchestrate.py)')
	return token


def read_swapper_model(override_ini):
	import configparser
	parser = configparser.ConfigParser()
	parser.read(override_ini)
	model = parser.get('processors', 'face_swapper_model', fallback='').strip()
	return model or DEFAULT_SWAPPER_MODEL


def scan_inputs(inputs_dir):
	inputs = Path(inputs_dir)
	override = inputs / 'override.ini'
	if not override.exists():
		sys.exit(f'missing {override}')
	sources = sorted(p for p in (inputs / 'sources').iterdir() if p.suffix.lower() in IMAGE_EXTS)
	targets = sorted(p for p in (inputs / 'targets').iterdir() if p.suffix.lower() in VIDEO_EXTS)
	if not sources or not targets:
		sys.exit('need at least one source and one target')
	return sources, targets, override


def s3_client(token):
	import boto3
	return boto3.client(
		's3',
		endpoint_url=f'https://dagshub.com/api/v1/repo-buckets/s3/{REPO_OWNER}',
		aws_access_key_id=token,
		aws_secret_access_key=token,
	)


def colab_env():
	"""On Windows, put the termios shim on PYTHONPATH so the Colab CLI imports."""
	env = os.environ.copy()
	if sys.platform == 'win32':
		shim = str(HERE / '_winshim')
		env['PYTHONPATH'] = shim + os.pathsep + env.get('PYTHONPATH', '')
	return env


def colab(*args, retries=3, allow_fail=False):
	"""Run a `colab` subcommand, retrying transient failures (e.g. a brief DNS /
	network blip). With allow_fail=True a persistent failure is swallowed (used
	for best-effort cleanup)."""
	cmd = ['colab', *map(str, args)]
	print(f'+ {" ".join(cmd)}', flush=True)
	for attempt in range(1, retries + 1):
		if subprocess.run(cmd, env=colab_env()).returncode == 0:
			return True
		if attempt < retries:
			print(f'  (failed; retry {attempt}/{retries - 1} in 5s)', flush=True)
			time.sleep(5)
	if allow_fail:
		print(f'  (giving up on `colab {args[0]}` — continuing)', flush=True)
		return False
	raise RuntimeError(f'`colab {args[0]}` failed after {retries} attempts')


def stop_session(session):
	"""Best-effort session teardown — never raises. Treats 'already gone' (no such
	session, or the runtime was already released) as success, and retries only
	genuine transient failures."""
	cmd = ['colab', 'stop', '-s', session]
	print(f'+ {" ".join(cmd)}', flush=True)
	for attempt in range(1, 4):
		result = subprocess.run(cmd, env=colab_env(), capture_output=True, text=True)
		out = f'{result.stdout or ""}{result.stderr or ""}'.lower()
		if result.returncode == 0:
			return
		if 'not found' in out or 'unassign' in out:
			print('  (session already released)', flush=True)
			return
		if attempt < 3:
			print('  (stop failed; retry in 5s)', flush=True)
			time.sleep(5)
	print('  (could not confirm stop — run `python orchestrate.py --stop` if a session lingers)', flush=True)


# ---------------------------------------------------------------- steps

def print_matrix(sources, targets, swapper_model):
	print(f'\nplanned outputs (model: {swapper_model}):')
	for target in targets:
		for source in sources:
			print(f'  {target.name}  x  {source.name}  ->  {compose_output_name(target.name, source.name, swapper_model)}')
	print(f'\n{len(sources) * len(targets)} combination(s)\n')


def clear_prefix(s3, prefix):
	"""Delete every object under prefix; return how many were removed."""
	removed = 0
	for page in s3.get_paginator('list_objects_v2').paginate(Bucket=REPO_NAME, Prefix=prefix):
		for obj in page.get('Contents', []):
			s3.delete_object(Bucket=REPO_NAME, Key=obj['Key'])
			removed += 1
	return removed


def upload_inputs(s3, sources, targets, override):
	# Wipe the previous batch first so the bucket exactly mirrors the local input
	# folder — otherwise stale sources/targets from an earlier run get reprocessed.
	for prefix in (f'{INPUT_PREFIX}/sources/', f'{INPUT_PREFIX}/targets/', f'{OUTPUT_PREFIX}/'):
		removed = clear_prefix(s3, prefix)
		if removed:
			print(f'  cleared {removed} stale object(s) under {prefix}', flush=True)
	for source in sources:
		s3.upload_file(str(source), REPO_NAME, f'{INPUT_PREFIX}/sources/{source.name}')
	for target in targets:
		s3.upload_file(str(target), REPO_NAME, f'{INPUT_PREFIX}/targets/{target.name}')
	s3.upload_file(str(override), REPO_NAME, f'{INPUT_PREFIX}/override.ini')
	print(f'✓ uploaded {len(sources)} source(s) + {len(targets)} target(s) + override.ini to s3://{REPO_NAME}/{INPUT_PREFIX}/', flush=True)


def _marker_key(name):
	return f'{OUTPUT_PREFIX}/{name}'


def _get_marker(s3, name):
	"""Return the parsed marker JSON, or None if it isn't there yet. A missing
	object on DagsHub surfaces as a generic 404 ClientError (not the modeled
	NoSuchKey), so treat any 404 as 'not present'; other errors propagate to the
	poll loop's retry handler."""
	import botocore.exceptions
	try:
		obj = s3.get_object(Bucket=REPO_NAME, Key=_marker_key(name))
		return json.loads(obj['Body'].read())
	except botocore.exceptions.ClientError as exc:
		code = str(exc.response.get('Error', {}).get('Code', ''))
		status = exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode')
		if code in ('NoSuchKey', '404', 'NotFound') or status == 404:
			return None
		raise


def clear_markers(s3):
	for name in (SUCCESS_MARKER, FAILED_MARKER):
		try:
			s3.delete_object(Bucket=REPO_NAME, Key=_marker_key(name))
		except Exception:
			pass


def launch_remote_batch(s3, token, session, gpu):
	"""Provision a session and kick off the batch DETACHED, so we never hold a
	live connection for the whole job. Completion is signalled by a bucket marker."""
	cfg = {
		'dagshub_token': token,
		'repo_owner': REPO_OWNER,
		'repo_name': REPO_NAME,
		'input_prefix': INPUT_PREFIX,
		'output_prefix': OUTPUT_PREFIX,
	}
	clear_markers(s3)  # drop any stale markers from a previous run
	stop_session(session)  # ensure no stale session with this name
	with tempfile.TemporaryDirectory() as tmp:
		cfg_path = Path(tmp) / 'batch_config.json'
		cfg_path.write_text(json.dumps(cfg))

		colab('new', '-s', session, '--gpu', gpu)
		colab('upload', '-s', session, str(cfg_path), '/content/batch_config.json')
		colab('upload', '-s', session, str(HERE / 'naming.py'), '/content/naming.py')
		colab('upload', '-s', session, str(HERE / 'v3_batch_run.py'), '/content/v3_batch_run.py')
		colab('upload', '-s', session, str(HERE / '_launch.py'), '/content/_launch.py')
		# short-lived exec: starts the detached job and returns in seconds
		colab('exec', '-s', session, '-f', str(HERE / '_launch.py'), retries=1)


def wait_for_completion(s3):
	"""Poll the bucket until the remote writes a success/failure marker. Each poll
	is an independent, retryable call — robust to transient network drops."""
	deadline = time.time() + POLL_TIMEOUT
	print(f'polling s3://{REPO_NAME}/{OUTPUT_PREFIX}/ for completion '
		  f'(every {POLL_INTERVAL}s, up to {POLL_TIMEOUT // 60} min)...', flush=True)
	while time.time() < deadline:
		try:
			failed = _get_marker(s3, FAILED_MARKER)
			if failed:
				raise RuntimeError(f'remote batch failed: {failed.get("error")}')
			success = _get_marker(s3, SUCCESS_MARKER)
			if success:
				print('✓ remote batch reported success', flush=True)
				return success
		except RuntimeError:
			raise
		except Exception as exc:  # transient: keep polling
			print(f'  (poll error, will retry): {exc}', flush=True)
		time.sleep(POLL_INTERVAL)
		print('  ... still processing', flush=True)
	raise TimeoutError(f'no completion marker after {POLL_TIMEOUT // 60} min')


def download_outputs(s3, output_names, out_dir):
	out = Path(out_dir)
	out.mkdir(parents=True, exist_ok=True)
	for name in output_names:
		s3.download_file(REPO_NAME, _marker_key(name), str(out / name))
		print(f'✓ downloaded {name}', flush=True)
	print(f'✓ {len(output_names)} result(s) in {out}', flush=True)


# ---------------------------------------------------------------- main

def main():
	ap = argparse.ArgumentParser()
	ap.add_argument('--inputs', help='folder with sources/, targets/, override.ini')
	ap.add_argument('--out', default='./batch_out', help='where to download results')
	ap.add_argument('--gpu', default='L4', help='Colab accelerator (T4, L4, A100, ...)')
	ap.add_argument('--session', default='ff', help='Colab session name')
	ap.add_argument('--dry-run', action='store_true', help='print the matrix and exit (no GPU/upload)')
	ap.add_argument('--stop', action='store_true', help='just stop the named session and exit (cleanup)')
	args = ap.parse_args()

	if args.stop:
		stop_session(args.session)
		return

	if not args.inputs:
		sys.exit('--inputs is required (or use --stop)')

	sources, targets, override = scan_inputs(args.inputs)
	swapper_model = read_swapper_model(override)
	print_matrix(sources, targets, swapper_model)
	if args.dry_run:
		return

	token = load_token()
	s3 = s3_client(token)
	upload_inputs(s3, sources, targets, override)
	try:
		launch_remote_batch(s3, token, args.session, args.gpu)
		success = wait_for_completion(s3)
		download_outputs(s3, success['outputs'], args.out)
	finally:
		stop_session(args.session)


if __name__ == '__main__':
	main()
