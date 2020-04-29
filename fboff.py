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
from urllib.request import urlopen

import ftfy
import clipboard


USAGE = """
fboff.py --import_fb      --input <json fb export directory> --output <reference html directory>
fboff.py --fixnum         --input <html directory> --output <html directory>
fboff.py --import_blogger --input <blogger post url> --output <reference html directory>
fboff.py --export_blogger --input <reference html directory>
    Copy blogger ready html into clipboard
"""


BEGIN = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8" /></head><body>'
END = '</body></end>'
SEP = '<hr color="#C0C0C0" size="1" />'
IMGPAT = '<a href="%s"><img src=%s width="400"/></a>'
JOURS = 'lundi mardi mercredi jeudi vendredi samedi dimanche'.split()
MOIS = 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre'.split()


def is_title(line):
    # risky. any line with a date is considered a title when in first line
    pattern = r'(?:%s )?(1er|\d|\d\d) (%s)\b' % ('|'.join(JOURS), '|'.join(MOIS))
    return re.search(pattern, line)


def date_from_title(title, year):
    pattern = r'(?:%s )?(1er|\d|\d\d) (%s)\b' % ('|'.join(JOURS), '|'.join(MOIS))
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
    record.append(IMGPAT % (uri, uri))
    return ts, record, uri


def parse_json(args, json_export_dir):
    records = dict()
    json_dir = os.path.join(json_export_dir, 'photos_and_videos', 'album')
    for json_file in glob.glob(os.path.join(json_dir, '*.json')):
        with open(json_file) as f:
            x = json.load(f)
        for photo in x['photos']:
            ts, record, uri = parse_json_photo(args, photo)
            records[ts] = (record, uri)
    for ts, (record, uri) in sorted(records.items()):
        yield ts, record, uri


def import_fb(args):
    os.makedirs(args.output, exist_ok=True)

    with open(os.path.join(args.output, 'index.htm'), 'wt', encoding='utf-8') as f:
        print(BEGIN, file=f)

        date = '2000-01-01'
        numimg = 0
        for ts, photo, uri in parse_json(args, args.input):
            for line in photo:
                if is_title(line):
                    date = date_from_title(line, 2019)  # TODO: paramétrer année
                    numimg = 0
                m = re.search(r'img src=([^ ]+)', line)  # TODO: prendre en compte img with ... src ...
                if m:
                    numimg += 1
                    name = m.group(1)
                    newname = date + '-' + str(numimg) + os.path.splitext(name)[1]
                    shutil.copy2(os.path.join(args.input, uri), os.path.join(args.output, newname))
                    line = IMGPAT % (newname, newname)
                print(line.strip(), file=f)
            print(file=f)

        print(END, file=f)


def html_records(url):
    with open(url, encoding='utf-8') as f:
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
    os.makedirs(args.output, exist_ok=True)

    date = '2000-01-01'
    numimg = 0
    with open(os.path.join(args.output, 'index.htm'), 'wt', encoding='utf-8') as f:
        print(BEGIN, file=f)
        print(file=f)

        for record in html_records(os.path.join(args.input, 'index.htm')):
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


def import_blogger(args):
    """
    Import html and photos from blogger and make the simplified page.
    """
    with urlopen(args.input) as u:
        buffer = u.read()
        buffer = buffer.decode('utf-8')

    tmp_name = os.path.join(args.output, 'tmp.htm')
    with open(tmp_name, 'wt', encoding='utf-8') as f:
        f.write(buffer)

    date = '2000-01-01'
    numimg = 0
    with open(os.path.join(args.output, 'index.htm'), 'wt', encoding='utf-8') as f:
        print(BEGIN, file=f)
        print(file=f)
        br = False

        for record in html_records(tmp_name):
            if is_title(record[1]):
                date = date_from_title(record[1], 2019)  # TODO: paramétrer année
                numimg = 0
            for line in record:
                m = re.search(r'img [^<>]*src="([^ ]+)"', line)
                if m:
                    numimg += 1
                    name = m.group(1)
                    newname = date + '-' + str(numimg) + os.path.splitext(name)[1]
                    line = IMGPAT % (newname, newname)
                    with urlopen(name) as u, open(os.path.join(args.output, newname), 'wb') as fimg:
                        fimg.write(u.read())

                # remove some tags
                tags = ('div', 'table', 'tbody', 'tr')
                pattern = '^<(' + '|'.join(tags) + '|/' + '|/'.join(tags) + ')'
                m = re.search(pattern, line)
                if m:
                    continue

                # remove consecutive br
                if line == '<br />\n':
                    if br:
                        continue
                    br = True
                else:
                    br = False

                print(line.strip(), file=f)
            print(file=f)

        print(END, file=f)
    os.remove(tmp_name)


def parse_command_line():
    parser = argparse.ArgumentParser(description=None, usage=USAGE)
    parser.add_argument('--import_fb', help='input json export, output html reference',
                        action='store_true', default=None)
    parser.add_argument('--fixnum', help='fix photo names renaming as date+index',
                        action='store_true', default=None)
    parser.add_argument('--export_blogger', help='input html reference, html extract blogger ready in clipboard',
                        action='store_true', default=False)
    parser.add_argument('--import_blogger', help='blogger post url, output html reference',
                        action='store_true', default=False)
    parser.add_argument('-i', '--input', help='input parameter',
                        action='store', default=None)
    parser.add_argument('-o', '--output', help='output parameter',
                        action='store', default=None)
    args = parser.parse_args()
    return args


def main():
    args = parse_command_line()

    if args.import_fb:
        import_fb(args)

    elif args.fixnum:
        fix_photo_names(args)

    elif args.export_blogger:
        prepare_for_blogger(args)

    elif args.import_blogger:
        import_blogger(args)


if __name__ == '__main__':
    main()
