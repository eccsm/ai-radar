# Custom PostgreSQL with pgvector
FROM postgres:16-alpine

# Install build dependencies
RUN apk add --no-cache --virtual .build-deps \
    build-base \
    git \
    ca-certificates \
    openssl-dev \
    curl-dev \
    postgresql-dev

# Clone and build pgvector with optimizations disabled
RUN git clone --branch v0.6.0 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && sed -i 's/^USE_LLVM.*$/USE_LLVM = 0/' Makefile \
    && sed -i 's/-march=native//' Makefile \
    && sed -i 's/-ftree-vectorize//' Makefile \
    && sed -i 's/-fassociative-math//' Makefile \
    && sed -i 's/-fno-signed-zeros//' Makefile \
    && sed -i 's/-fno-trapping-math//' Makefile \
    && make USE_LLVM=0 \
    && make install

# Cleanup
RUN apk del .build-deps

# Set required environment variables
ENV POSTGRES_DB=ai_radar
ENV POSTGRES_USER=ai
ENV POSTGRES_PASSWORD=ai_pwd