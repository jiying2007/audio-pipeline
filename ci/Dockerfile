FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac

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
