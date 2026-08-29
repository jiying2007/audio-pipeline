FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       alsa-utils \
       build-essential \
       ca-certificates \
       ccache \
       clang \
       clang-tools \
       cmake \
       curl \
       gcc-aarch64-linux-gnu \
       gcc-arm-linux-gnueabihf \
       gcovr \
       git \
       jq \
       libasound2-dev \
       libc6-dev-arm64-cross \
       libc6-dev-armhf-cross \
       ninja-build \
       pkg-config \
       python3 \
       python3-pip \
       qemu-user \
       xz-utils \
    && rm -rf /var/lib/apt/lists/*

ENV CCACHE_DIR=/ccache \
    CCACHE_COMPRESS=true \
    CCACHE_MAXSIZE=1G

WORKDIR /workspace
