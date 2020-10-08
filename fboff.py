"""
An offliner of facebook photos using fb json export

*.json
        produit de l'export facebook, non éditable (ex. pas de correction
        d'orthographe), lu en objets Post
objets Post
        représentation interne, sauvée en index.htm
index.htm
        repésentation externe, éditable, relu en objets Post
"""

import os
import argparse
import json
import glob
import shutil
import re
import io
import pprint
from collections import defaultdict
from datetime import datetime
from urllib.request import urlopen
from lxml import objectify


import ftfy
import clipboard


USAGE = """
fboff.py --import_fb      --input <json directory> --output <html directory> [--rename_img]
fboff.py --import_blogger --input <blogger  url>   --output <html directory> [--rename_img]
fboff.py --export_blogger --input <html directory>
fboff.py --rename_img     --input <html directory>
"""


# -- Post objects -------------------------------------------------------------

"""
Date des posts.

Les posts sont l'unité de publication. A l'export json, ce sont les éléments de
premiers niveaux. Dans mon use case, un post peut ne pas avoir de titre et/ou un
post peut ne pas avoir de photos.
On veut donner une date à chaque post avec les contraintes suivantes :
- si le post a un titre, sa date est la date du titre (donc le timestamp du post
  ne convient pas)
- si le post a une photo, sa date est la date de prise de vue (on admet que
  c'est vérifié dans le use case)
- les dates doivent respectées l'ordre des posts, autrement dit l'ordre des
  timestamps de post (on admet que c'est vérifié dans le use case).

Le problème se pose dans le cas des posts sans date, ni photo (cas des cartes
par exemple qu'on souhaite renommer de façon cohérente avec les cartes). Dans ce
cas, on attribue la date du post précédent.

Dernier problème, si le premier post n'a pas de date, on lui atribue la date du
post suivant.

Pour simplifier, même chose mais on ne considère que la date dans le titre (donc
pas de problème de cohérence).

Problème de l'année ...
"""


BEGIN = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8" /></head><body>'
END = '</body></end>'
SEP = '<hr color="#C0C0C0" size="1" />'
IMGPAT = '<a href="%s"><img src=%s width="400"/></a>'
IMGPAT2 = '<a href="file:///%s"><img src=file:///%s width="300"/></a>'
TITLEIMGPAT = '<a href="%s"><img src=%s width="400" title="%s"/></a>'
JOURS = 'lundi mardi mercredi jeudi vendredi samedi dimanche'.split()
MOIS = 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre'.split()

# diminution de l'espace entre images, on utilise :
# "display: block;", "margin-bottom: 0em;" et "font-size: 0;"
# "display: block;" dans img : espacement correct ordi mais pas centré téléphone
# "display: block;" dans a   : ok

BIMGPAT = '''\
<div class="separator" style="clear: both; text-align: center;">
<a href="%s" style="clear: left; margin-bottom: 0em; margin-right: 1em; font-size: 0; display: block;">
<img border="0" src="%s" width="640" />
</a></div>
'''
CAPTION_PAT = '''\
<div class="separator" style="clear: both; text-align: center;">
%s
</div>
'''


class Image:
    def __init__(self, caption, uri, creation):
        self.caption = caption
        self.uri = uri
        self.creation = creation

class Post:
    def __init__(self, timestamp, title, text, photos):
        """
        posts are extracted from fb json extract which is a list of post descriptions (fbpost).
        At initialisation, the object if made of the following values:
            timestamp = fbpost[timestamp]
            title     = first line of fbpost[data][post] if dedicated syntax
            text      = rest of fbpost[data][post]
            images    = list of Image objects
            dcim      = list of Image objects
        """
        self.timestamp = timestamp
        self.title = title
        self.text = text
        self.images = photos
        self.dcim = []
        if self.timestamp is not None:
            # timestamp peut être None si lu dans html
            self.timestamp_str = datetime.utcfromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S')

    @classmethod
    def from_fb_json(cls, json_post):
        timestamp = int(json_post['timestamp'])
        if json_post['data']:
            title, text = parse_json_text(json_post['data'][0]['post'])
        else:
            title, text = None, []
        images = list()
        if 'attachments' in json_post:
            for attachment in json_post['attachments']:
                if attachment:
                    if attachment['data']:
                        for data in attachment['data']:
                            uri = data['media']['uri']
                            try:
                                creation = data['media']['media_metadata']['photo_metadata']['taken_timestamp']
                            except:
                                creation = None
                            try:
                                caption = data['media']['description']
                                if json_post['data'] and caption == json_post['data'][0]['post']:
                                    caption = None
                            except:
                                caption = None
                            images.append(Image(caption, uri, creation))
        return cls(timestamp, title, text, images)

    @classmethod
    def from_html(cls, html_post):
        timestamp = None  # pour le moment
        title = None
        text = ''
        images = list()
        for line in html_post:
            m = re.match('<b>([^<>]+)</b>', line)
            if m:
                title = m.group(1)
                continue
            m = re.search('<img [^<>]*src="?([^ "]+)"? width="\d+"(?: title="([^"]+)")?\s*/>', line)
            if m:
                images.append(Image(m.group(2), m.group(1), None))
                continue
            m = re.match('<[^<>]+>', line)
            if m:
                # ignore les autres balises
                continue
            # tout le reste c'est le texte sauf la ligne vide de séparation à la fin
            text += line
        text = re.sub(r'\n$', '', text)
        text = text.split('\n') if text else []
        return cls(timestamp, title, text, images)

    def to_html(self, target='local'):
        if target == 'local':
            return self.to_html_local()
        if target == 'blogger':
            return self.to_html_blogger()

    def to_html_local(self):
        html = list()
        html.append(SEP)
        if self.title:
            html.append(f'<b>{self.title}</b>')
            html.append('<br />')
        for line in self.text:
            html.append(line)
        if self.text:
            html.append('<br />')
        for image in self.images:
            if not image.caption:
                html.append(IMGPAT % (image.uri, image.uri))
            else:
                html.append(TITLEIMGPAT % (image.uri, image.uri, image.caption))
        if self.dcim:
            html.append(SEP)
        for image in self.dcim:
            html.append(IMGPAT2 % (image.uri, image.uri))
        return html

    def to_html_blogger(self):
        html = list()
        html.append(SEP)
        if self.title:
            html.append(f'<b>{self.title}</b>')
            html.append('<br />')
        for line in self.text:
            html.append(line)
        if self.text:
            html.append('<br />')
        for image in self.images:
            html.append(BIMGPAT % (image.uri, image.uri))
            if image.caption:
                html.append(CAPTION_PAT % image.caption)
        return html


# -- Handling of dates and sequential image names -----------------------------


def set_year_in_posts(posts, year):
    # nécessite un paramètre si on ne peut pas trouver l'année (blogger)
    if year is not None:
        for post in posts:
            post.year = year
        return

    # première passe pour donner une année aux posts avec photo (prend l'année
    # de la première photo)
    for post in posts:
        post.year = None
        for image in post.images:
            if image.creation:
                post.year = datetime.utcfromtimestamp(image.creation).strftime('%Y')
                break

    # cas du premier post sans année, on lui donne l'année du premier post avec année
    if posts[0].year is None:
        for post in posts[1:]:
            if post.year:
                posts[0].year = post.year
                break

    # deuxième passe pour donner aux posts sans année l'année du post précédent
    year = posts[0].year
    for post in posts[1:]:
        if post.year is None:
            post.year = year
        else:
            year = post.year


def set_date_in_posts(posts):
    # première passe pour donner une date aux posts avec titre
    for post in posts:
        post.date = None
        if post.title:
            post.date = date_from_title(post.title, post.year)

    # cas du premier post sans date, on lui donne la date du premier post avec date
    if posts[0].date is None:
        for post in posts[1:]:
            if post.date:
                posts[0].date = post.date
                break

    # deuxième passe pour donner aux posts sans date la date du post précédent
    date = posts[0].date
    for post in posts[1:]:
        if post.date is None:
            post.date = date
        else:
            date = post.date


def set_sequential_image_names(posts):
    """Numérotage séquentiel des images à l'intérieur d'un post
    """
    last_image = dict()
    for post in posts:
        if post.date not in last_image:
            last_image[post.date] = 0
        for image in post.images:
            last_image[post.date] += 1
            image.newname = post.date + '-' + str(last_image[post.date]) + os.path.splitext(image.uri)[1]


def rename_images(posts, input_path, output_path):
    for post in posts:
        for image in post.images:
            shutil.copy2(os.path.join(input_path, image.uri), os.path.join(output_path, image.newname))
            image.uri = image.newname


# -- Facebook json parser -----------------------------------------------------


def parse_json_text(text):
    text = ftfy.ftfy(text)
    text = text.splitlines()
    if is_title(text[0]):
        return text[0], text[1:]
    else:
        return None, text


def is_title(line):
    # dubious. any line with a date is considered a title when in first line
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


def parse_json(args, json_export_dir):
    """
    Generate Post objects from fb json export directory in chronological order.
    json files are located in json_export_dir/posts, picture paths are relative
    to <json_export_dir>
    """
    posts = dict()
    json_dir = os.path.join(json_export_dir, 'posts')
    for json_file in glob.glob(os.path.join(json_dir, '*.json')):
        with open(json_file) as f:
            for json_post in json.load(f):
                post = Post.from_fb_json(json_post)
                posts[post.timestamp] = post

    if not posts:
        print('Warning: No posts found in', json_dir)
    else:
        ordered_posts = [post for ts, post in sorted(posts.items())]

        set_year_in_posts(ordered_posts)
        set_date_in_posts(ordered_posts)
        set_sequential_image_names(ordered_posts)

        if args.rename_img:
            rename_images(ordered_posts, args.input, args.output)

        return ordered_posts


# -- html parser --------------------------------------------------------------


def parse_html(args, url):
    """
    Generate Post objects from html (local or blogger). Posts are in
    chronological order.
    """
    posts = list()
    with open(url, encoding='utf-8') as f:
        line = next(f)
        while SEP not in line:
            line = next(f)
        record = [line]
        for line in f:
            if SEP not in line and END not in line:
                record.append(line)
            else:
                posts.append(Post.from_html(record))
                record = [line]
    return posts


# -- html printer -------------------------------------------------------------


def print_html_to_stream(posts, stream, target='local'):
    print(BEGIN, file=stream)

    for post in posts:
        for line in post.to_html(target):
            print(line.strip(), file=stream)
        print(file=stream)

    print(END, file=stream)


def print_html(posts, html_name, target='local'):
    if html_name:
        with open(html_name, 'wt', encoding='utf-8') as f:
            print_html_to_stream(posts, f, target)
            return None
    else:
        with io.StringIO() as f:
            print_html_to_stream(posts, f, target)
            return f.getvalue()


# -- Compose html with blogger image urls -------------------------------------


def parse_images_url(args):
    imgdata = dict()
    with open(os.path.join(args.input, 'uploaded-images.html'), encoding='utf-8') as f:
        s = f.read()

        # XML is required to have exactly one top-level element (Stackoverflow)
        s = f'<tmp>{s}</tmp>'

        x = objectify.fromstring(s)
        for elem_div in x.iterchildren(tag='div'):
            elem_a = next(elem_div.iterchildren(tag='a'))
            href = elem_a.get("href")
            imgdata[os.path.basename(href)] = (
                href,
                elem_a.img.get("src"),
                elem_a.img.get("data-original-height"),
                elem_a.img.get("data-original-width")
            )
    return imgdata


def compose_blogger_html(args):
    imgdata = parse_images_url(args)
    posts = parse_html(args, os.path.join(args.input, 'index.htm'))

    for post in posts:
        for image in post.images:
            if image.uri not in imgdata:
                print('Image missing: ', image.uri)
            else:
                img_url, resized_url, original_height, original_width = imgdata[image.uri]
                image.uri = img_url

    return print_html(posts, '', target='blogger').splitlines()


# -- Import/export for blogger-------------------------------------------------


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

    posts = parse_html(args, tmp_name)
    os.remove(tmp_name)

    for post in posts:
        for image in post.images:
            print(image.uri)
            with urlopen(image.uri) as u, open(os.path.join(args.output, os.path.basename(image.uri)), 'wb') as fimg:
                fimg.write(u.read())
            image.uri = os.path.basename(image.uri)

    # posts are chronologicaly ordered in blogger
    ordered_posts = posts

    set_year_in_posts(ordered_posts, args.year)
    set_date_in_posts(ordered_posts)
    set_sequential_image_names(ordered_posts)

    if args.rename_img:
        rename_images(ordered_posts, args.output, args.output)

    print_html(ordered_posts, os.path.join(args.output, 'index.htm'))


def prepare_for_blogger(args):
    """
    Export blogger html to clipboard.
    If --full, export complete html, otherwise export html extract ready to
    paste into blogger edit mode.
    """
    html = compose_blogger_html(args)

    if args.full is False:
        tags = ('html', 'head', 'body')
        html = [line for line in html if not any(_ in line for _ in tags)]

    clipboard.copy('\n'.join(html))


# -- Commands -----------------------------------------------------------------


def import_fb(args):
    os.makedirs(args.output, exist_ok=True)
    print_html(parse_json(args, args.input), os.path.join(args.output, 'index.htm'))


def test(args):
    posts = parse_html(args, os.path.join(args.input, 'index.htm'))
    print_html(posts, 'tmp.htm')


def extend_index(args):
    bydate = defaultdict(list)
    for image in glob.glob(os.path.join(args.imgsource, '*.jpg')):
        # IMG_20190221_065509.jpg
        name = os.path.basename(image)
        date = name.split('_')[1]
        bydate[date].append(Image(None, image, None))
    for date, liste in bydate.items():
        bydate[date] = liste  # sorted(liste)

    posts = parse_html(args, os.path.join(args.input, 'index.htm'))
    for post in posts:
        if post.title:
            date = date_from_title(post.title, year='2019')
            if date:
                date = date.replace('-', '')
                post.dcim = bydate[date]
    print_html(posts, os.path.join(args.input, 'index-x.htm'))


def rename_images(args):
    posts = parse_html(args, os.path.join(args.input, 'index.htm'))
    rename_images(posts, args.input, args.output)
    print_html(posts, os.path.join(args.output, 'index.htm'))


# -- OBSOLETE -----------------------------------------------------------------


def html_records(url):
    """
    OBSOLETE

    relecture html local
    """
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
    """
    OBSOLETE
    """
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


# -- Main ---------------------------------------------------------------------


def parse_command_line():
    parser = argparse.ArgumentParser(description=None, usage=USAGE)
    parser.add_argument('--import_fb', help='input json export, output html reference',
                        action='store_true', default=None)
    parser.add_argument('--import_blogger', help='blogger post url, output html reference',
                        action='store_true', default=False)
    parser.add_argument('--rename_img', help='fix photo names renaming as date+index',
                        action='store_true', default=None)
    parser.add_argument('--export_blogger', help='input html reference, html extract blogger ready in clipboard',
                        action='store_true', default=False)
    parser.add_argument('--extend', help='extend image set, source in --imgsource',
                        action='store_true', default=False)
    parser.add_argument('--test', help='',
                        action='store_true', default=False)
    parser.add_argument('-i', '--input', help='input parameter',
                        action='store', default=None)
    parser.add_argument('--year', help='year',
                        action='store', default=None)
    parser.add_argument('-o', '--output', help='output parameter',
                        action='store', default=None)
    parser.add_argument('--full', help='full html (versus blogger ready html)',
                        action='store_true', default=False)
    parser.add_argument('--imgsource', help='image source for extended index',
                        action='store', default=None)
    args = parser.parse_args()
    return args


def main():
    args = parse_command_line()

    if args.import_fb:
        import_fb(args)

    elif args.import_blogger:
        import_blogger(args)

    elif args.rename_img:
        rename_images(args)

    elif args.export_blogger:
        prepare_for_blogger(args)

    elif args.test:
        test(args)

    elif args.extend:
        extend_index(args)


if __name__ == '__main__':
    main()
