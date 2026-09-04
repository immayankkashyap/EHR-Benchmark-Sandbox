FROM ubuntu:22.04

# Install Squid proxy package
RUN apt-get update && \
    apt-get install -y --no-install-recommends squid ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy custom Squid configuration and entrypoint
COPY squid.conf /etc/squid/squid.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose proxy port
EXPOSE 3128

ENTRYPOINT ["/entrypoint.sh"]
