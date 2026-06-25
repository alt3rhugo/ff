# -*- coding: utf-8 -*-
"""FFusion 3.5.0 — Version 2 (headless, automatic, no human in the loop)

Pulls the source image + target video from DagsHub storage, runs FaceFusion
headless (no UI), then pushes the result back to DagsHub storage.

Prerequisites:
  1. The fork is already cloned + installed (run CELL 1 and CELL 2 of the V1
     notebook first, or inline the same two steps before this file).
  2. A Colab Secret named DAGSHUB_USER_TOKEN holds a *valid* DagsHub token.

SECURITY: the previous hardcoded token (6803b7a0...) is COMPROMISED because it
was committed to a GitHub-remote repo. Rotate it on DagsHub (User Settings ->
Tokens) and store the new one as a Colab Secret. Never hardcode it again.
"""

# === CELL A: SYSTEM DEPS + DAGSHUB CLIENT ===
get_ipython().system('curl -s https://rclone.org/install.sh | sudo bash')
get_ipython().system('apt-get update -y && apt-get install -y fuse3')
get_ipython().run_line_magic('pip', 'install -q "dagshub[jupyter]"')

# === CELL B: CONFIG + TOKEN (from Colab Secret, no interactive auth) ===
import os
import shutil

from google.colab import userdata

os.environ["DAGSHUB_USER_TOKEN"] = userdata.get("DAGSHUB_USER_TOKEN")

REPO_OWNER = "zbynja"
REPO_NAME = "ff"
REPO = f"{REPO_OWNER}/{REPO_NAME}"

# Paths inside DagsHub storage (adjust to match what you upload there).
DAGSHUB_SOURCE = "source.jpg"          # the face to swap in
DAGSHUB_TARGET = "target.mp4"          # the video to process
DAGSHUB_OUTPUT = "output/output.mp4"   # where the result is written back

LOCAL_SOURCE = "/content/input/source.jpg"
LOCAL_TARGET = "/content/input/target.mp4"
LOCAL_OUTPUT = "/content/output/output.mp4"

# === CELL C: DOWNLOAD SOURCE + TARGET FROM DAGSHUB ===
import dagshub
import dagshub.storage

mount_path = dagshub.storage.mount(REPO)
print("Mounted at:", mount_path)
print("Root contents:", os.listdir(mount_path))

os.makedirs("/content/input", exist_ok=True)
os.makedirs("/content/output", exist_ok=True)

shutil.copy(os.path.join(mount_path, DAGSHUB_SOURCE), LOCAL_SOURCE)
shutil.copy(os.path.join(mount_path, DAGSHUB_TARGET), LOCAL_TARGET)
print(f"✓ Downloaded source -> {LOCAL_SOURCE}")
print(f"✓ Downloaded target -> {LOCAL_TARGET}")

# === CELL D: HEADLESS RUN (no UI, no clicks) ===
# Mirrors the tuned settings from the previous notebook.
get_ipython().system(f'''python facefusion.py headless-run \\
  --execution-providers cuda \\
  -s {LOCAL_SOURCE} \\
  -t {LOCAL_TARGET} \\
  -o {LOCAL_OUTPUT} \\
  --processors face_swapper face_enhancer \\
  --face-swapper-model hyperswap_1c_256 \\
  --face-swapper-pixel-boost 512x512 \\
  --face-swapper-weight 0.65 \\
  --face-enhancer-model gpen_bfr_512 \\
  --face-enhancer-blend 12 \\
  --face-enhancer-weight 0.1 \\
  --face-selector-mode one \\
  --face-detector-score 0.65 \\
  --face-landmarker-score 0.65 \\
  --face-detector-angles 0 90 270 \\
  --face-mask-blur 0.35 \\
  --face-mask-types box occlusion''')

assert os.path.exists(LOCAL_OUTPUT), f"Headless run produced no output at {LOCAL_OUTPUT}"

# === CELL E: UPLOAD RESULT TO DAGSHUB STORAGE BUCKET (S3) ===
# Writes the output into the SAME DagsHub Storage Bucket that CELL C reads the
# input from -- not the Git/DVC repo. DagsHub buckets are S3-compatible; the
# DagsHub token serves as both the access key and the secret key.
get_ipython().run_line_magic('pip', 'install -q boto3')
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://dagshub.com/api/v1/repo-buckets/s3/{REPO_OWNER}",
    aws_access_key_id=os.environ["DAGSHUB_USER_TOKEN"],
    aws_secret_access_key=os.environ["DAGSHUB_USER_TOKEN"],
)

# Bucket name == repo name; key == the path inside the bucket.
s3.upload_file(LOCAL_OUTPUT, REPO_NAME, DAGSHUB_OUTPUT)
print(f"✓ Uploaded result -> s3://{REPO_NAME}/{DAGSHUB_OUTPUT} (DagsHub Storage Bucket)")
