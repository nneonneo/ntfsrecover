from __future__ import unicode_literals, print_function
import struct
import collections
import glob
import fnmatch
import os
import sys
import codecs

def doseek(f, n):
    if sys.platform == 'win32':
        # Windows raw disks can only be seeked to a multiple of the block size
        BLOCKSIZE = 512
        na, nb = divmod(n, BLOCKSIZE)
        f.seek(na * BLOCKSIZE)
        if nb:
            f.read(nb)
    else:
        f.seek(n)

def readat(f, n, s):
    pos = f.tell()
    doseek(f, n)
    res = f.read(s)
    doseek(f, pos)
    return res

def parseFilename(s):
    ref, = struct.unpack('<Q', s[:8])
    flen = ord(s[64:65])
    fn = s[66:66 + flen*2].decode('UTF-16-LE')
    return ref, fn

def parseRaw(s):
    return s

ATTR_INFO = {
     0x10: ('standard_info', 'STANDARD_INFORMATION ', None),
     0x20: ('attr_list', 'ATTRIBUTE_LIST ', None),
     0x30: ('filename', 'FILE_NAME ', parseFilename),
     0x40: ('vol_ver', 'VOLUME_VERSION', None),
     0x40: ('obj_id', 'OBJECT_ID ', None),
     0x50: ('security', 'SECURITY_DESCRIPTOR ', None),
     0x60: ('vol_name', 'VOLUME_NAME ', None),
     0x70: ('vol_info', 'VOLUME_INFORMATION ', None),
     0x80: ('data', 'DATA ', None),
     0x90: ('index_root', 'INDEX_ROOT ', None),
     0xA0: ('index_alloc', 'INDEX_ALLOCATION ', None),
     0xB0: ('bitmap', 'BITMAP ', None),
     0xC0: ('sym_link', 'SYMBOLIC_LINK', None),
     0xC0: ('reparse', 'REPARSE_POINT ', None),
     0xD0: ('ea_info', 'EA_INFORMATION ', None),
     0xE0: ('ea', 'EA ', None),
     0xF0: ('prop_set', 'PROPERTY_SET', None),
    0x100: ('log_util', 'LOGGED_UTILITY_STREAM', None),
}

def parse_varint(v):
    if not v:
        return 0
    return int(codecs.encode(v[::-1], 'hex'), 16)

def read_runlist(f, bpc, runlist):
    out = bytearray()
    for rlen, roff in runlist:
        out += readat(f, roff * bpc, rlen * bpc)
    return bytes(out)

def parse_attr(f, bpc, chunk):
    type, size, nonres, namelen, nameoff = struct.unpack('<iiBBH', chunk[:12])

    if namelen:
        name = chunk[nameoff:nameoff+namelen*2].decode('UTF-16-LE')
    else:
        name = None

    stype, sname, sparser = ATTR_INFO.get(type, ('unk_%d' % type, str(type), parseRaw))
    if sparser is None:
        sparser = parseRaw
    sname = sname.strip()

    if nonres:
        rloff = struct.unpack('<H', chunk[32:34])[0]
        size_actual = struct.unpack('<Q', chunk[48:56])[0]
        rlpos = rloff
        runlist = []
        curoff = 0
        while rlpos < len(chunk):
            header = ord(chunk[rlpos:rlpos+1])
            if not header:
                break
            rlpos += 1
            lenlen = header & 0xf
            offlen = header >> 4
            if rlpos + lenlen + offlen > len(chunk):
                print("Warning: invalid runlist header %02x (runlist %s)" % (header, codecs.encode(chunk[rloff:], 'hex')), file=sys.stderr)
                break
            thislen = parse_varint(chunk[rlpos:rlpos+lenlen])
            rlpos += lenlen
            thisoff = parse_varint(chunk[rlpos:rlpos+offlen])
            if thisoff and (thisoff & (1 << (8 * offlen - 1))):
                thisoff -= 1 << (8 * offlen)
            rlpos += offlen
            curoff += thisoff
            runlist.append((thislen, curoff))

        attrdata = lambda: sparser(read_runlist(f, bpc, runlist)[:size_actual])
    else:
        attrlen, attroff = struct.unpack('<IH', chunk[16:22])
        data = chunk[attroff:attroff+attrlen]
        attrdata = lambda: sparser(data)

    return sname, name, attrdata

def usa_fixup(chunk, chunkoff, usa_ofs, usa_count):
    chunk = bytearray(chunk)
    if usa_ofs == 0 or usa_count == 0:
        return chunk

    upos = usa_ofs
    usa_num = chunk[upos:upos+2]
    upos += 2
    for i in range(len(chunk) // 512):
        cpos = i*512+510
        if chunk[cpos:cpos+2] != usa_num:
            print("Warning: bad USA data at MBR offset %d - disk corrupt?" % (chunkoff + cpos), file=sys.stderr)
        else:
            chunk[cpos:cpos+2] = chunk[upos:upos+2]
        upos += 2
    return chunk

def parse_file(f, chunkoff, bpc, chunk):
    magic, usa_ofs, usa_count, lsn, seq, link, attr_offset = struct.unpack(
        '<IHHQHHH', chunk[:22])
    attrs = collections.defaultdict(dict)
    try:
        chunk = usa_fixup(chunk, chunkoff, usa_ofs, usa_count)
    except Exception as e:
        print("File at offset %d: failed to perform USA fixup: %s" % (chunkoff, e), file=sys.stderr)

    pos = attr_offset
    while 1:
        if pos > len(chunk) - 12:
            # Uhoh, corruption?
            break
        type, size, nonres, namelen, nameoff = struct.unpack('<iIBBH', chunk[pos:pos+12])
        if type == -1:
            break

        try:
            sname, name, data = parse_attr(f, bpc, chunk[pos:pos+size])
            attrs[sname][name] = data
        except Exception as e:
            print("File at offset %d: failed to parse attr type=%d pos=%d: %s" % (chunkoff, type, pos, e), file=sys.stderr)

        pos += size
    return attrs

def parse_mft(f, bpc, mft):
    out = []
    for i in range(len(mft) // 1024):
        if i % 791 == 0:
            sys.stderr.write("\rParsing MFT: %d/%d" % (i, len(mft) // 1024))
            sys.stderr.flush()

        chunk = mft[i*1024:(i+1)*1024]
        if chunk[:4] == b'FILE':
            out.append(parse_file(f, i * 1024, bpc, chunk))
        else:
            out.append(None)
    sys.stderr.write("\rParsing MFT: Done!              \n")
    sys.stderr.flush()
    return out

def read_mft(f, bpc, mft_cluster, clusters_per_mft):
    print("Loading MBR from cluster %d" % mft_cluster, file=sys.stderr)
    mft = readat(f, mft_cluster * bpc, clusters_per_mft * bpc)
    try:
        mftattr = parse_file(f, 0, bpc, mft[:1024])
        newmft = mftattr['DATA'][None]()
        if len(newmft) < len(mft):
            raise Exception("$MFT truncated")
        mft = newmft
    except Exception as e:
        print("WARNING: Failed to load $MFT (%s), proceeding with partial MFT." % e, file=sys.stderr)

    return mft
    
def get_filepath(mft, i):
    bits = []
    while 1:
        parent, name = mft[i]['FILE_NAME'][None]()
        if name == '.':
            break
        bits.append(name)
        i = parent & 0xffffffffffff
    return bits[::-1]

def open_output_file(destfn):
    if not os.path.isfile(destfn):
        return open(destfn, 'wb')

    t = 0
    while True:
        fn = destfn + '_%04d' % t
        if not os.path.isfile(fn):
            return open(fn, 'wb')
        t += 1
    raise OSError("File exists.")

def save_file(mfti, destfn):
    if '/' in destfn:
        try:
            os.makedirs(destfn.rsplit('/', 1)[0])
        except OSError:
            pass

    with open_output_file(destfn) as outf:
        outf.write(mfti['DATA'][None]())

    for ads in mfti['DATA']:
        if ads is None:
            continue
        with open_output_file(destfn + '~' + ads) as outf:
            outf.write(mfti['DATA'][ads]())

def parse_args(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Recover files from an NTFS volume")
    parser.add_argument('--sector-size', type=int,
        help='Sector size in bytes (default: trust filesystem)')
    parser.add_argument('--cluster-size', type=int,
        help='Cluster size in sectors (default: trust filesystem)')
    parser.add_argument('--mft', type=argparse.FileType('rb'),
        help='Use given file as MFT')
    parser.add_argument('--save-mft', type=argparse.FileType('wb'),
        help='Write extracted MFT to given file')
    parser.add_argument('-p', '--pattern', action='append',
        help='Recover files matching pattern (glob()); can be specified multiple times')
    parser.add_argument('-o', '--outdir',
        help='Output directory (default .)')
    parser.add_argument('disk', help='NTFS partition (e.g. /dev/disk*, \\\\.\\Harddisk*Partition*)')
    return parser.parse_args(argv)

def main(argv):
    args = parse_args(argv)

    f = open(args.disk, 'rb')

    if args.outdir:
        try:
            os.makedirs(args.outdir)
        except OSError:
            pass
        os.chdir(args.outdir)

    # parse essential details of the MBR
    if readat(f, 3, 8) != b'NTFS    ':
        raise ValueError("Not an NTFS disk???")

    bps, spc = struct.unpack('<HB', readat(f, 0xb, 3))
    if args.sector_size:
        bps = args.sector_size
    if args.cluster_size:
        spc = args.cluster_size
    bpc = bps * spc

    mft_clust, mftmirr_clust, clust_per_mft = struct.unpack('<QQB', readat(f, 0x30, 17))

    print("Reading MFT", file=sys.stderr)
    if args.mft:
        mftbytes = args.mft.read()
    else:
        mftbytes = read_mft(f, bpc, mft_clust, clust_per_mft)

    if args.save_mft:
        args.save_mft.write(mftbytes)

    mft = parse_mft(f, bpc, mftbytes)
    for i, file in enumerate(mft):
        try:
            fn = file['FILE_NAME'][None]()[1]
        except Exception as e:
            continue

        try:
            fullpath = '/'.join(get_filepath(mft, i))
        except Exception as e:
            fullpath = '__ORPHANED__/' + fn

        if not args.pattern:
            print(fullpath)
            continue

        for pat in args.pattern:
            pat = pat.lower().encode('utf8')
            if fnmatch.fnmatch(fn.lower().encode('utf8'), pat) or fnmatch.fnmatch(fullpath.lower().encode('utf8'), pat):
                print("Recovering", fullpath, end=' ')
                try:
                    save_file(file, fullpath)
                except Exception as e:
                    print("failed:", e)
                else:
                    print("Success!")

if __name__ == '__main__':
    import sys
    exit(main(sys.argv[1:]))
