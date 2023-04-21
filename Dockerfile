# Base image with CUDA runtime
FROM nvidia/cuda:11.0.3-runtime-ubuntu20.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -fs /usr/share/zoneinfo/UTC /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata


# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    wget \
    build-essential \
    zlib1g-dev \
    libncurses5-dev \
    libgdbm-dev \
    libnss3-dev \
    libssl-dev \
    libreadline-dev \
    libffi-dev \
    libsqlite3-dev \
    libbz2-dev

# Download and install Python 3.10.8
RUN wget https://www.python.org/ftp/python/3.10.8/Python-3.10.8.tgz && \
    tar xzf Python-3.10.8.tgz && \
    cd Python-3.10.8 && \
    ./configure --enable-optimizations && \
    make -j "$(nproc)" && \
    make altinstall && \
    cd .. && \
    rm -rf Python-3.10.8.tgz Python-3.10.8

# Set Python 3.10 as default
RUN ln -s /usr/local/bin/python3.10 /usr/local/bin/python3 && \
    ln -s /usr/local/bin/python3.10 /usr/local/bin/python && \
    ln -s /usr/local/bin/pip3.10 /usr/local/bin/pip3 && \
    ln -s /usr/local/bin/pip3.10 /usr/local/bin/pip

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

# Expose and start the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
