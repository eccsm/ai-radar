# Fixed Dockerfile for NATS Exporter
FROM golang:1.22-alpine AS builder
RUN apk add --no-cache git
RUN git clone https://github.com/nats-io/prometheus-nats-exporter.git /src
WORKDIR /src
RUN go mod download && go build -o nats-exporter .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /src/nats-exporter .
EXPOSE 7777

# Use ENTRYPOINT instead of CMD for better flexibility
ENTRYPOINT ["./nats-exporter"]
# Default CMD can be overridden in docker-compose.yml
CMD ["-varz", "-connz", "-subz", "-jsz=all", "http://nats:8222"]