ARG GO_VERSION=1.22

# Build stage
FROM golang:${GO_VERSION}-alpine AS builder
WORKDIR /src

# Download dependencies first (better layer caching)
COPY go.mod go.sum ./
RUN go mod download

# Copy source
COPY . .

# Build static binary for linux/amd64 (default)
ENV CGO_ENABLED=0
RUN GOOS=linux GOARCH=${TARGETARCH:-amd64} go build -o /out/ws-bench .

# Runtime stage
FROM alpine:3.19
RUN apk add --no-cache ca-certificates
WORKDIR /app

COPY --from=builder /out/ws-bench /usr/local/bin/ws-bench

ENTRYPOINT ["/usr/local/bin/ws-bench"]
CMD ["-help"]
