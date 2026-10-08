FROM docker.io/library/rust@sha256:d8f0d5c09580253ecdd6d6894ff112b2b760683ff2a74585e5189f2578728ce4

RUN dpkg --add-architecture arm64 && dpkg --add-architecture riscv64 \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential git ca-certificates curl cmake ninja-build pkg-config \
    python3 python3-venv python3-yaml python3-tomli qemu-user file \
    gcc-aarch64-linux-gnu g++-aarch64-linux-gnu \
    gcc-riscv64-linux-gnu g++-riscv64-linux-gnu \
    libglib2.0-dev:arm64 libglib2.0-dev:riscv64 \
    libpixman-1-dev:arm64 libpixman-1-dev:riscv64 \
    libepoxy-dev:arm64 libepoxy-dev:riscv64 \
    libvulkan-dev:arm64 libvulkan-dev:riscv64 \
    libslirp-dev:arm64 libslirp-dev:riscv64 \
    libssl-dev:arm64 libssl-dev:riscv64 \
    libpcap-dev:arm64 libpcap-dev:riscv64 \
    libsamplerate0-dev:arm64 libsamplerate0-dev:riscv64 \
    libcurl4-openssl-dev:arm64 libcurl4-openssl-dev:riscv64 \
    libx11-dev:arm64 libx11-dev:riscv64 \
    libxext-dev:arm64 libxext-dev:riscv64 \
    libxrandr-dev:arm64 libxrandr-dev:riscv64 \
    libxcursor-dev:arm64 libxcursor-dev:riscv64 \
    libxi-dev:arm64 libxi-dev:riscv64 \
    libxss-dev:arm64 libxss-dev:riscv64 \
    libxfixes-dev:arm64 libxfixes-dev:riscv64 \
    libxtst-dev:arm64 libxtst-dev:riscv64 \
    libgl1-mesa-dri:arm64 libgl1-mesa-dri:riscv64 \
    libglx-mesa0:arm64 libglx-mesa0:riscv64 \
    && rm -rf /var/lib/apt/lists/*

RUN rustup toolchain install 1.96.0 --profile minimal --component rustfmt --component clippy \
    && rustup target add --toolchain 1.96.0 aarch64-unknown-linux-gnu riscv64gc-unknown-linux-gnu
