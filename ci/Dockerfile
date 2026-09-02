FROM ubuntu:26.04@sha256:2260313b31c8c011cd2eebe728008efac1b3982be73eb71348ea2648d2c0e09b

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
