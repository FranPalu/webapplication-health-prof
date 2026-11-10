FROM orthancteam/orthanc@sha256:06b8baab0c63cd58de5474a74b64096a82ea3f7eab2aa471e217cc48c9ae11bf
COPY orthanc.json /claria-orthanc.json
COPY start.py /claria-pacs-start.py
ENTRYPOINT ["python3", "/claria-pacs-start.py"]
