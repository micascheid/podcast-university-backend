# Using image as used in local testing with slim
FROM python:3.10.8-slim
# FROM nvidia/cuda:11.4.1-cudnn8-runtime-ubuntu20.04
# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image
ENV APP_HOME /app
ENV OPENAI_KEY "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"
ENV ALLOWABLE_DOMAIN "https://podcast-university.web.app"
ENV PORT 8080
WORKDIR $APP_HOME
COPY . /app

# Install production dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg

RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
# ENV CUDA_VISIBLE_DEVICES=0
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
