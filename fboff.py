"""
An offliner of facebook photos using fb json export
"""

import os
import argparse
import json
import glob
import shutil
import re
from datetime import datetime

import ftfy
import clipboard


USAGE = """
fboff.py --html --input <json fb export directory> --output <reference html directory>
fboff.py --fixnum --input <html directory> --output <html directory>
fboff.py --blogger --input <reference html directory> --output <blogger ready html>
"""


BEGIN = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8" /></head><body>'
END = '</body></end>'
SEP = '<hr color="#C0C0C0" size="1" />'
IMGPAT = '<a href="%s"><img src=%s width="400"/></a>'
JOURS = 'lundi mardi mercredi jeudi vendredi samedi dimanche'.split()
MOIS = 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre'.split()


def is_title(line):
    return 'km' in line or any(_ in line for _ in MOIS)


def date_from_title(title, year):
    pattern = r'(?:%s )?(1er|\d|\d\d) (%s)' % ('|'.join(JOURS), '|'.join(MOIS))
    m = re.search(pattern, title)
    if not m:
        return None
    else:
        day = 1 if m.group(1) == '1er' else int(m.group(1))
        month = MOIS.index(m.group(2)) + 1
        return f'{year}-{month:02}-{day:02}'


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

    #destdir = os.path.join(args.output, datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d'))
    destdir = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
    new_uri = os.path.join(destdir, os.path.basename(uri))
    record.append(IMGPAT % (new_uri, new_uri))
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


def html_records(args):
    with open(os.path.join(args.input, 'index.htm'), encoding='utf-8') as f:
        line = next(f)
        while SEP not in line:
            line = next(f)
        record = [line]
        for line in f:
            if SEP not in line and END not in line:
                record.append(line)
            else:
                yield record
                record = [line]


def fix_photo_names(args):
    date = '2000-01-01'
    numimg = 0
    with open(os.path.join(args.output, 'index.htm'), 'wt', encoding='utf-8') as f:
        print(BEGIN, file=f)
        print(file=f)

        for record in html_records(args):
            if is_title(record[1]):
                date = date_from_title(record[1], 2019)  # TODO: paramétrer année
                numimg = 0
            for line in record:
                m = re.search(r'img src=([^ ]+)', line)
                if m:
                    numimg += 1
                    name = m.group(1)
                    newname = date + '-' + str(numimg) + os.path.splitext(name)[1]
                    line = IMGPAT % (newname, newname)
                    shutil.copy2(os.path.join(args.input, name), os.path.join(args.output, newname))

                print(line.strip(), file=f)

        print(END, file=f)


def prepare_for_blogger(args):
    """
    Export simplified html to clipboard (remove html, head, body and img tags)
    """
    tags = ('html', 'head', 'body', 'img')
    with open(os.path.join(args.input, 'index.htm'), encoding='utf-8') as f:
        buffer = [line for line in f if not any(_ in line for _ in tags)]
    clipboard.copy(''.join(buffer))


def parse_command_line():
    parser = argparse.ArgumentParser(description=None, usage=USAGE)
    parser.add_argument('--html', help='input json export, output html reference',
                        action='store', default=None)
    parser.add_argument('--fixnum', help='fix photo names renaming as date+index',
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
        make_html_reference(args)

    if args.fixnum:
        fix_photo_names(args)

    elif args.blogger:
        prepare_for_blogger(args)


if __name__ == '__main__':
    main()
