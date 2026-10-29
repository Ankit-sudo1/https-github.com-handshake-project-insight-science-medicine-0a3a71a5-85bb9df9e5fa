# Agent image: Python numerical stack and a C compiler, plus the clinic's records (environment/data).
# Nothing from the verifier or the reference solution is copied.
FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.4.4 scipy==1.17.1

WORKDIR /app
COPY data /app/data
# the instruction tells the agent not to modify the records; make that true rather than trusted.
# Nothing in /app/data is read by the verifier, which grades only the submitted artifact against its own
# protected copy of the hidden values, so tampering here could not affect grading in any case.
RUN chmod -R a-w /app/data
