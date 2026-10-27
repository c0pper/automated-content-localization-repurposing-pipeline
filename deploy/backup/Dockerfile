FROM pgsty/silo:RELEASE.2026-10-26T00-00-00Z AS silo

FROM postgres:16-alpine

RUN apk add --no-cache tzdata bash

COPY --from=silo /usr/bin/mcli /usr/local/bin/mcli
COPY deploy/backup/backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/mcli

ENTRYPOINT ["/usr/local/bin/backup.sh"]
