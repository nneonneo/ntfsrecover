## Introduction

Dead-simple (and somewhat stupid) NTFS data-recovery program. Works with Python 2.7 or Python 3.x, no dependencies. It can be used to recover deleted files or files off of damaged drives, although recovery quality will depend on how badly the file data has been damaged or overwritten.

Warning: to avoid data loss, please use this on a clean clone of the disk (e.g. by using `ddrescue`), rather than on the original disk. This program will read large swaths of the disk (specifically the entire Master File Table), which may stress an already damaged disk. Making a clean copy ensures that you can rerun the program as many times as you want without further data loss.

## Motivation
A friend recently had an NTFS drive crash on him, and I happened to have learned about NTFS literally the day before (thanks MMA/TWCTF 2016!). So I put that to good use by writing this NTFS data recovery tool.

## Disk paths

You may specify a path to a partition image file (previously created using e.g. `ddrescue`), or a raw disk path to read directly from the physical disk. Note that the latter should be used with extreme caution if the disk has failed, as it may stress an already-damaged disk to the point of failure.

Specifying disk paths is OS-specific:

### Windows
On Windows disk paths should be specified using the device path:

    \\.\Harddisk*Partition*

For example, `\\.\Harddisk0Partition1` for the first partition on the first drive (note that `Harddisk` is 0-indexed while `Partition` is 1-indexed).

The program `diskpart` may be used to view the disk and partition numbers - use `list disk`, followed by `select disk N`, followed by `list partition`.

### Linux
On Linux, disk paths should be specified using `/dev` paths, which depends on the device type. `fdisk -l`, `parted -l` or `lsblk` can show you which device path to use.

### macOS
On macOS, disk paths should be specified using `/dev/diskNsM` paths. `diskutil list` will show you all partitions and their corresponding disk paths.

## Usage

First, make a backup of your MFT:

    python ntfsrecover.py /dev/diskX --save-mft mft

This will also print out the full paths to every single file on your disk. (This will be verbose as hell, but it's very useful!). Next, you can use `--pattern` in conjunction with `--mft` to selectively recover files. (`--mft` saves the program from having to read the MFT again; only file data will need to be read).

    python ntfsrecover.py /dev/diskX --mft mft --pattern "*.jpg" --outdir recovered

You can specify `--pattern` multiple times to recover multiple different kinds of files in one run. It will match either the full path *or* the filename; thus, you can do things like `--pattern "*/My Documents/*"`.
