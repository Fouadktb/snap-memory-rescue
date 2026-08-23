# Third-party tools

Snap Memory Rescue can use system-installed tools or private copies provided for convenience.

## ExifTool

On Windows, the launcher downloads the official ExifTool executable package directly from [exiftool.org's SourceForge distribution](https://sourceforge.net/projects/exiftool/files/). The archive is pinned to a specific version and SHA-256 hash before extraction. Its license files remain alongside the installed executable.

ExifTool is created by Phil Harvey and is distributed under the same terms as Perl itself. See the [ExifTool website](https://exiftool.org/) and the license files included in its distribution.

## imageio-ffmpeg and FFmpeg

The Python dependency [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) provides platform-specific FFmpeg binaries and is distributed under the BSD 2-Clause License.

FFmpeg itself is distributed under the LGPL or GPL depending on how a particular binary was configured. License and source information are available from the [FFmpeg project](https://ffmpeg.org/legal.html) and the [imageio binary repository](https://github.com/imageio/imageio-binaries).
