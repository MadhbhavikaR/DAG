# Hardware reference

## Known target

- NVR: Hikvision DS-7616NXI-K1
- NVR firmware: V4.83.010, build 241118
- NVR HTTP address: 192.168.100.103:80
- Allocated NVR channels: 13
- RTSP source: NVR; RTSP port must be verified
- Jetson: Nano 4GB, JetPack 4.6.6
- Cameras: 11 Hikvision DS-2CD1041G2-LIU and 2 CP Plus CP-UNC-TA41L3C-D-LQ

## Discovery still required

- Actual channel-to-camera mapping.
- RTSP port and enabled transport.
- ISAPI account permissions and authentication behavior.
- Actual alertStream payload variants and event types.
- Jetson storage capacity, power/thermal condition and available RAM.
- Sustained decoder and inference capacity.

Do not infer a physical camera mapping from channel count or camera inventory order.
