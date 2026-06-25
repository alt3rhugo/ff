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
    - settings override idea:
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

- I want to run an agent that would run this whole thing from my local, so here I would have a folder with source images / target images and the setting file. Then the agent would:
    1. upload all these to dagshub
    2. run the colab (in headless batch mode)
    3. when done, download the files back to dagshub and disconnect the colab env
    4. download the result videos (all of them) from dagshub to my local
- I want the filenames to keep their original filenames and compound them. e.g.:
    - for source file [ls 65.jpg] and video files [25-lnka-cc.0756-0838.mp4] and [20-lnka-cc.0644-0725.mp4] I would get:
        - [25-lnka-cc.0756-0838 ls65b.mp4]
        - [20-lnka-cc.0644-0725 ls65b.mp4]
        - the final letter 'b' is based on the face-swapper-model setting
            - for face-swapper-model [hyperswap_1c_256] we would use 'c', e.g. [25-lnka-cc.0756-0838 ls65c.mp4]
            - for face-swapper-model [hyperswap_1b_256] we would use 'b', e.g. [25-lnka-cc.0756-0838 ls65b.mp4]
            - for face-swapper-model [hyperswap_1a_256] we would use 'a', e.g. [25-lnka-cc.0756-0838 ls65a.mp4]
            - for face-swapper-model [inswapper_128] we would use 'in', e.g. [25-lnka-cc.0756-0838 ls65in.mp4]
            - for face-swapper-model [inswapper_128_fp16] we would use 'in', e.g. [25-lnka-cc.0756-0838 ls65in.mp4]
- If the file already has a compound name - which means it is running a Round 2 with a different source image over it, this would be added with a hyphen at the end in this way
    - e.g. for a new source file [ls 33.jpg] being used over the target video file [25-lnka-cc.0756-0838 ls65b.mp4] it would be 
        - [25-lnka-cc.0756-0838 ls65b-ls33b.mp4] or
        - [25-lnka-cc.0756-0838 ls65b-ls33c.mp4]
        - again based on the face-swapper-model being used

