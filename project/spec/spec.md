## current workflow
- I start Google Colab, see my current notebook [project\google-colab]
    - I made certain changes to the FaceFusion repo
    - I added Gradio support so that I can use the frontend for the FF app
- I manually upload the target video file
- once uploaded I go to generated URL gradio link 
- I upload the source image file
- I make changes to settings and run the merging process
- once the process is done, I would manually download the file using the Colab filesystem UX - click on the download link

## desired state
There I several milestones / versions I wish to achieve

### version 1
- all my custom changes merged
- one tuned-up working package / repo with the latest dependencies
- videos uploaded using the upload button

#### goal
- Merge all my changes into this repo and then reference this repo url instead of the original one [https://github.com/facefusion/facefusion.git]
- Make sure all the latest dependencies are loaded and working
- Make sure gradio works as well

### version 2
- input videos copied over from DagsHub storage and also copied back to this storage once they are finished, see the current code snippet with real token key [project\google-colab\dagshub.py]

#### goal
- the same as version 1, only the video upload is automatic
- the output video is automatically copied over to dagsHub storage
- make sure no human in the loop is needed (e.g. for token authorization with manual link for DagsHub or similar)

2