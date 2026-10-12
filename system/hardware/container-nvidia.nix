# NVIDIA GPU of the server through the NVIDIA container runtime
# (--runtime=nvidia, NVIDIA_DRIVER_CAPABILITIES=all; helpws
# plan-wsgnomebox): the driver comes from the server on every start, so the
# hook of ws-container-init fixes up GBM and /proc on every start.
{ file, ... }:
{
  files = [
    (file "/usr/local/lib/ws-container/init.d/50-nvidia" "system/files/container/50-nvidia" "0755")
  ];
}
