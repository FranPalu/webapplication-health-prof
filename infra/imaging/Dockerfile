FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pip==26.2.0 setuptools==84.1.0
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 torchvision==0.29.2
RUN pip install --no-cache-dir torchxrayvision==1.4.0
COPY run.py contract.py convert_legacy.py test_conversion.py /
USER 65534:65534
ENTRYPOINT ["python", "/run.py"]
