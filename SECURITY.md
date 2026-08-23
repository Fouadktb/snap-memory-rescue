# Security and privacy

Snap Memory Rescue is designed to process personal archives locally. It binds to `127.0.0.1` by default and has no telemetry or remote upload service.

On its first Windows launch, the app downloads the official ExifTool archive over HTTPS and verifies its pinned SHA-256 digest before extracting it. FFmpeg is installed through the platform-specific `imageio-ffmpeg` Python wheel. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for sources and licensing.

Do not run it with a public bind address such as `0.0.0.0`, and do not share a real Snapchat export in a public issue. Exports may contain private photos, videos, locations, account history, and expiring download links.

To report a vulnerability, use GitHub's private vulnerability reporting feature for this repository instead of opening a public issue.
