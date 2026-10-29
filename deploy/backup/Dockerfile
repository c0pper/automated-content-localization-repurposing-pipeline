FROM pgsty/silo:RELEASE.2026-10-26T00-00-00Z AS silo

FROM postgres:16-alpine

RUN apk add --no-cache tzdata bash

COPY --from=silo /usr/bin/mcli /usr/local/bin/mcli
COPY deploy/backup/backup.sh /usr/local/bin/backup.sh
# Strip CRs so a stale CRLF working copy cannot ship a broken shebang (#48).
RUN sed -i 's/\r$//' /usr/local/bin/backup.sh \
    && chmod +x /usr/local/bin/backup.sh /usr/local/bin/mcli

ENTRYPOINT ["/usr/local/bin/backup.sh"]
