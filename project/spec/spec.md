## current workflow
- I start Google Colab, see my current notebook [project\google-colab\version-0\FFusion_3_5_0_copy_1.ipynb]
    - I made certain changes to the FaceFusion repo
    - I added Gradio support so that I can use the frontend for the FF app
- I manually upload the target video file during the runtime
- once uploaded I go to generated URL gradio link 
- I upload the source image file via the Gradio UI
- I make changes to settings and run the merging process
- once the process is done, I would manually download the file using the Colab filesystem UX - click on the download link

## desired state
There are several milestones / versions I wish to achieve incrementally:

---

### version 1
- all my custom changes merged
- one tuned-up working package / repo with the latest dependencies
- the target video will be uploaded to Dagshub file storage beforehand
- the source image  will be uploaded to Dagshub file storage beforehand
- when clicking Run ALL - the runtime would upload the target video and the source image from the Dagshub storage and present the user with Gradio link

**goal:**
- Merge all my changes into this repo and then reference this repo url instead of the original one [https://github.com/facefusion/facefusion.git]
- Make sure all the latest dependencies are loaded and working
- Make sure gradio works as well

---

### version 2
- input videos auto-copied over from DagsHub storage and also auto-copied back to this storage once they are finished

**goal:**
- the same as version 1, only the video upload is automatic
- the output video is automatically copied over back to dagsHub storage once processed and finished
- make sure no human in the loop is needed (e.g. for token authorization with manual link for DagsHub or video upload or similar)

---

### version 3
- batch processing

**goal:**
- I am able to process batch of videos for one source image
- I am also able to process one video with several source images
- in both cases I want to also load the settings override (maybe a yaml file or similar) - these would be the same for the whole batch (e.g. not change per each combination)

settings override idea:
    e.g. this is the default settings in the colab cell:

```python
# === CELL 6: HEADLESS RUN (no UI, no clicks) ===
!python facefusion.py headless-run \
  --execution-providers cuda \
  -s {LOCAL_SOURCE} \
  -t {LOCAL_TARGET} \
  -o {LOCAL_OUTPUT} \
  --processors face_swapper face_enhancer \
  --face-enhancer-model gpen_bfr_512 \
  --face-swapper-model hyperswap_1c_256 \
  --face-swapper-pixel-boost 512x512 \
  --face-enhancer-blend 65 \
  --face-enhancer-weight 0.65 \
  --face-swapper-weight 0.65 \
  --face-mask-blur 0.65
```

and I have these setting in my override file:
```code
--face-swapper-model hyperswap_1b_256 \
--face-mask-blur 0.8
```
-- these would be used insted when running the facefusion runtime