FROM python:3.12.8-slim AS builder

# Install dependencies
RUN apt-get update && apt-get install -y git

# Install Poetry
RUN pip install poetry==1.7.1

# Environment variables for Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

# Copy project files
COPY . /app

# Install project dependencies
RUN poetry install && rm -rf $POETRY_CACHE_DIR

# Use a non-root user for the runtime stage
FROM python:3.12.1-slim AS runtime

# Install the required packages for AWS CLI
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    groff \
    less \
    bash \
    unzip \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws

# Environment variables to create user dynamically
# Previous versions passed these values using something like --build-arg USER_ID=$(shell id -u) --build-arg GROUP_ID=$(shell id -g)
# We do not do that becaus macos and linux returns different values and at the end the mcos default group conflict with the target image group.
# If you are unhappy with the values below, change it and explain why. 
ARG USER_ID=1000
ARG GROUP_ID=1000

# Ensure that GID is not 0 to avoid conflict with the root group
RUN if [ "${GROUP_ID}" -ne 0 ]; then \
        if ! getent group ${GROUP_ID} > /dev/null; then \
            groupadd -g ${GROUP_ID} fred-user; \
        fi; \
    else \
        groupadd -g 1000 fred-user; \
        GROUP_ID=1000; \
    fi

# Ensure that UID is not 0 to avoid conflict with the root user
RUN if [ "${USER_ID}" -ne 0 ]; then \
        if ! id -u ${USER_ID} > /dev/null 2>&1; then \
            useradd -u ${USER_ID} -g ${GROUP_ID} -m fred-user; \
        fi; \
    else \
        useradd -u 1000 -g ${GROUP_ID} -m fred-user; \
        USER_ID=1000; \
    fi

# Create necessary directories and set permissions
RUN mkdir -p /app && chown -R fred-user:fred-user /app

# Switch to the non-root user
USER fred-user

# Environment variables for the application. The values below correspond to the
# default values used by the application.
ENV SERVER_ADDRESS=0.0.0.0
ENV LISTEN_PORT=8000
ENV BASE_URL_PATH=/fred

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

ENV RIFT_ENV=/app/fred
ENV RESOURCES=/app/config
ENV TESTS=/app/tests
ENV MAKEFILE=/app/Makefile

# Copy necessary files from the builder stage
COPY --from=builder --chown=${USER_ID}:${GROUP_ID} ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY --from=builder --chown=${USER_ID}:${GROUP_ID} ${RIFT_ENV} ${RIFT_ENV}
COPY --from=builder --chown=${USER_ID}:${GROUP_ID} ${RESOURCES} ${RESOURCES}
COPY --from=builder --chown=${USER_ID}:${GROUP_ID} ${TESTS} ${TESTS}
COPY --from=builder --chown=${USER_ID}:${GROUP_ID} ${MAKEFILE} ${MAKEFILE}

WORKDIR /app

# Set the entrypoint
ENTRYPOINT ["python", "fred/main.py"]
