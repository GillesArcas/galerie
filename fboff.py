import os
import argparse
import json
import pprint
import ftfy
import glob
import shutil
from datetime import datetime


USAGE = """
fboff.py --html --input <json fb export directory> --output <reference html directory>
fboff.py --blogger --input <reference html directory> --output <blogger ready html>
"""


BEGIN = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8" /></head><body>'
END = '</body></end>'
SEP = '<hr color="#C0C0C0" size="1" />'
MOIS = 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre'.split()


def parse_json_photo(args, photo):
    record = list()
    uri = photo['uri']
    timestamp = photo['creation_timestamp']
    ts = int(timestamp)
    print(datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'))
    if 'description' in photo:
        record.append(SEP)
        description = ftfy.ftfy(photo['description'])
        description = description.splitlines()
        print(description[0])
        if is_title(description[0]):
            record.append(f'<b>{description[0]}</b>')
            record.append('<br />')
            for line in description[1:]:
                record.append(line)
            record.append('<br />')
        else:
            for line in description:
                record.append(line)
            record.append('<br />')
    destdir = os.path.join(args.output, datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d'))
    new_uri = os.path.join(destdir, os.path.basename(uri))
    record.append(f'<a href="{new_uri}"><img src={new_uri} width="400"/></a>')
    return ts, record, uri


def parse_json(args, json_export_dir):
    records = dict()
    json_dir = os.path.join(json_export_dir, 'photos_and_videos', 'album')
    for json_file in glob.glob(os.path.join(json_dir, '*.json')):
        print('---', json_file)
        with open(json_file) as f:
            x = json.load(f)
        for photo in x['photos']:
            ts, record, uri = parse_json_photo(args, photo)
            records[ts] = (record, uri)
    for ts, (record, uri) in sorted(records.items()):
        yield ts, record, uri


def make_html_reference(args):
    with open(os.path.join(args.output, 'index.htm'), 'wt', encoding='utf-8') as f:
        print(BEGIN, file=f)

        for ts, photo, uri in parse_json(args, args.input):
            for line in photo:
                print(line, file=f)
            print(file=f)
            destdir = os.path.join(args.output, datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d'))
            os.makedirs(destdir, exist_ok=True)
            shutil.copy2(os.path.join(args.input, uri), destdir)

        print(END, file=f)


def parse_command_line():
    usage = USAGE
    parser = argparse.ArgumentParser(description=None, usage=USAGE)
    parser.add_argument('--html', help='input json export, output html reference',
                        action='store', default=None)
    parser.add_argument('--blogger', help='input html reference, output html extract vlogger ready',
                        action='store', default=None)
    parser.add_argument('--input', help='input directory',
                        action='store', default=None)
    parser.add_argument('--output', help='output directory',
                        action='store', default=None)
    args = parser.parse_args()
    return args


def main():
    args = parse_command_line()

    if args.html:
        return make_html_reference(args)

    elif args.blogger:
        return None


if __name__ == '__main__':
    main()
