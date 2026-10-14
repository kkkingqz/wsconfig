# syntax=docker/dockerfile:1
# Image of a container host (ws help plan-wsgnomebox), built from one commit
# of the checkout: ws container build sends `git archive` of it as the
# context. Everything a recreated container needs is here; /nix, the home,
# the RDP state and /config are directories of the server.
ARG HOST=wsgnomebox

# The system tree of the host, as ws system tree builds it.
FROM docker.io/nixos/nix:latest AS system
ARG HOST
COPY . /src
RUN nix --extra-experimental-features 'nix-command flakes' build \
        --out-link /result "path:/src#system-${HOST}" \
    && cp -rL /result /tree

FROM docker.io/library/ubuntu:26.04
ARG HOST
ARG DEBIAN_FRONTEND=noninteractive
ENV container=docker
STOPSIGNAL SIGRTMIN+3

# What lib/apt.bash itself runs: sudo, add-apt-repository.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sudo software-properties-common ca-certificates gpg

# Only the files of the apt step: a commit that does not touch them keeps
# this layer.
COPY lib/apt.bash /ws/lib/apt.bash
COPY container/image-setup /ws/container/image-setup
COPY system/apt.txt /ws/system/apt.txt
COPY apt.txt /ws/apt.txt
COPY hosts/${HOST}/ /ws/hosts/${HOST}/
RUN /ws/container/image-setup "${HOST}" \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /ws

COPY container/system-install /usr/local/sbin/ws-system-install
RUN --mount=type=bind,from=system,source=/tree,target=/tree \
    /usr/local/sbin/ws-system-install /tree

EXPOSE 3389
ENTRYPOINT ["/usr/local/sbin/ws-container-init"]
CMD ["/sbin/init"]
