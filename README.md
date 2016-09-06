## Introduction

Dead-simple (and somewhat stupid) NTFS data-recovery program.

A friend recently had an NTFS drive crash on him, and I happened to have learned about NTFS literally the day before (thanks MMA/TWCTF 2016!). So I put that to good use by writing this NTFS data recovery tool.

Warning: to avoid data loss, please use this on a clean clone of the disk (e.g. by using `ddrescue`), rather than on the original disk. This program will read large swaths of the disk (specifically the entire Master File Table), which may stress an already damaged disk. Making a clean copy ensures that you can rerun the program as many times as you want without further data loss.

## Usage

First, make a backup of your MFT:

    python ntfsrecover.py /dev/diskX --save-mft mft

This will also print out the full paths to every single file on your disk. (This will be verbose as hell, but it's very useful!). Next, you can use `--pattern` in conjunction with `--mft` to selectively recover files. (`--mft` saves the program from having to read the MFT again; only file data will need to be read).

    python ntfsrecover.py /dev/diskX --mft mft --pattern '*.jpg' --outdir recovered

You can specify `--pattern` multiple times to recover multiple different kinds of files in one run. It will match either the full path *or* the filename; thus, you can do things like `--pattern '*/My Documents/*'`.
