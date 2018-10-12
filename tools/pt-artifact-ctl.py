#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

from optparse import OptionParser, OptionGroup, IndentedHelpFormatter
import os
import sys
import logging

if sys.version_info >= (3, 0):
    import http.client as httplib
else:
    import httplib

bindir, basename = os.path.split(sys.argv[0])
sys.path.insert(0, os.path.join(bindir, ".."))

from perftrackerlib.client import ptServer, ptArtifact, ptRuntimeException, ptJsonEncoder

from perftrackerlib import perftrackerlib_require_version
perftrackerlib_require_version('0.0.30')

class formatter(IndentedHelpFormatter):
    def __init__(self):
        IndentedHelpFormatter.__init__(self, indent_increment=2, max_help_position=30, width=80, short_first=1)

    def format_description(self, description):
        if not description:
            return ""
        ret = "Description:"
        if description.startswith("\n"):
            ret += description
        else:
            ret += "\n%s\n" % description
        return ret


def run(opts, args, abort):
    pt_server = ptServer(opts.pt_server_url)

    if len(args) == 0:
        abort("command is not specified")

    if args[0] in ("upload", "update") and len(args) >= 2 and len(args) <= 3:
        if args[0] == "upload":
            uuid = args[2] if len(args) >= 3 else None
            filepath = args[1]
        elif args[0] == "update":
            uuid = args[1]
            filepath = None

        filename = opts.filename if opts.filename else (os.path.basename(filepath) if filepath else None)
        artifact = ptArtifact(pt_server, uuid1=uuid)

        artifact.filename = filename
        artifact.mime = opts.mime
        artifact.description = opts.description
        artifact.ttl_days = opts.ttl
        artifact.inline = opts.inline
        artifact.compression = opts.compression

        if args[0] == "upload":
            resp = artifact.upload(filepath)
        elif args[0] == "update":
            resp = artifact.update()

    elif args[0] == "link" and len(args) == 3:
        resp = ptArtifact(pt_server, uuid1=args[1]).link([args[2]])
    elif args[0] == "unlink" and len(args) == 3:
        resp = ptArtifact(pt_server, uuid1=args[1]).unlink([args[2]])
    elif args[0] == "delete" and len(args) == 2:
        resp = ptArtifact(pt_server, uuid1=args[1]).delete()
    elif args[0] == "info" and len(args) == 2:
        resp = ptArtifact(pt_server, uuid1=args[1]).info()
        if resp.status_code == httplib.OK:
            print(ptJsonEncoder.pretty(resp.json))
            return
    elif args[0] == "download" and len(args) == 3:
        uuid = args[1]
        filepath = args[2]
        resp = ptArtifact(pt_server, uuid1=uuid).download(filepath)
        if resp.status_code == httplib.OK:
            print("Artifact UUID %s saved to %s (%d bytes)" % (uuid, filepath, len(resp.content)))
            return
    elif args[0] == "dump" and len(args) == 2:
        uuid = args[1]
        resp = ptArtifact(pt_server, uuid1=uuid).download()
        if resp.status_code == httplib.OK:
            print(resp.text)
            return
    elif args[0] == "list":
        try:
            limit = int(args[1]) if len(args) >= 2 else 10
        except ValueError as e:
            abort("list limit must be a number, got: '%s'" % str(args[1]))
        resp, artifacts = ptArtifact(pt_server).list(limit)

        if resp.status_code == httplib.OK:
            fmt = "%36s %10s %10s %6s %5s %7s %24s  %s"
            print(fmt % ("UUID", "UPLOADED", "EXPIRES", "INLINE", "COMPR", "SIZE KB", "MIME", "NAME"))
            for a in artifacts:
                print(fmt % (a.uuid,
                             a.uploaded_dt.strftime("%Y-%m-%d"),
                             a.expires_dt.strftime("%Y-%m-%d"),
                             "Yes" if a.inline else "No",
                             "Yes" if a.compression else "No",
                             "%.1f" % (a.size / 1024.0),
                             a.mime,
                             a.filename + (" (%s)" % a.description if a.description else "")))
            return
    else:
        abort()

    print("status: %d - %s" % (resp.status_code, resp.json['message']))


def main():
    usage = "usage: %prog [options] command [command parameters]"

    description = """
    %prog [options] upload ARTIFACT_FILE_TO_UPLOAD [ARTIFACT_UUID]
    %prog [options] update ARTIFACT_UUID
    %prog [options] delete ARTIFACT_UUID
    %prog [options] info ARTIFACT_UUID
    %prog [options] link ARTIFACT_UUID OBJECT_UUID
    %prog [options] unlink ARTIFACT_UUID OBJECT_UUID
    %prog [options] list [LIMIT]
    %prog [options] download ARTIFACT_UUID ARTIFACT_FILE_TO_SAVE
    """

    op = OptionParser(description=description, usage=usage, formatter=formatter())
    op.add_option("-v", "--verbose", default=0, action="count", help="enable verbose mode")
    op.add_option("-p", "--pt-server-url", default="http://127.0.0.1:9000", help="perftracker url, default %default")

    og = OptionGroup(op, "'upload' and 'update' options")
    og.add_option("-d", "--description", help="artifact description (i")
    og.add_option("-m", "--mime", default=None, help="artifact mime type, default is guessed or "
                                                     "'application/octet-stream'")
    og.add_option("-f", "--filename", help="override artifact file name by given name")
    og.add_option("-z", "--compression", action="store_true", help="inline decompression on every file view or "
                                                                   "download")
    og.add_option("-i", "--inline", default=False, action="store_true", help="inline view in browser "
                                                                             "(do not download on click)")
    og.add_option("-t", "--ttl", default=180, help="time to live (days), default=%default, 0 - infinite")
    op.add_option_group(og)

    opts, args = op.parse_args()

    loglevel = logging.DEBUG if opts.verbose >= 2 else (logging.INFO if opts.verbose == 1 else logging.WARNING)
    logging.basicConfig(level=loglevel, format="%(asctime)s - %(module)17s - %(levelname).3s - %(message)s",
                        datefmt='%H:%M:%S')

    def abort(msg=None):
        op.print_usage()
        print(description)
        if msg:
            print("error: %s" % msg)
        sys.exit(-1)

    try:
        run(opts, args, abort)
    except ptRuntimeException as e:
        logging.error(str(e))
        sys.exit(-1)


if __name__ == "__main__":
    main()
