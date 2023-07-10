FROM python:3.7

#
# Simply our base packages that are required for this application, these should not change very often or between images
#
RUN echo "[INFO]::[installing]::[base packages]" \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -o Dpkg::Options::="--force-confold" -y --force-yes --no-install-recommends --no-install-suggests \
        ntp \
    && apt-get autoclean && apt-get clean && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*