"""
Media directory and diary organizer. Handle a markdown file organized by dates,
each day described by a text and a subset of the medias (photos and movies).

The markdown file can be:
* edited manually (very basic syntax),
* created from the media directory,

The markdown file can be exported to:
* an html file with the text and subset of medias associated with each day,
* the previous html file extended with all medias in the media directory,
* an html file ready to import into Blogger.
"""

import sys
import os
import argparse
import glob
import shutil
import re
import io
import time
import bisect
import locale
import textwrap
import html
import base64
from collections import defaultdict
from datetime import date, datetime
from subprocess import check_output, CalledProcessError, STDOUT
from urllib.request import urlopen

import clipboard
import PIL
from PIL import Image, ImageChops
from lxml import objectify
import markdown


USAGE = """
journal --create     --output <directory> --imgsource <media directory>
journal --html       --input  <directory>
journal --extend     --input  <directory> --imgsource <media directory>
journal --rename_img --input  <directory>
journal --blogger    --input  <directory> --url <url> [--check] [--full]
"""


# -- Post objects -------------------------------------------------------------


FAVICON_BASE64 = '''\
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAAAAAA6mKC9AAAArUlEQVR42mP8z4AKmBjIF/ix7jhCYG
rrdSC5FigKFdC8xnH/OYMRAwMHAwPjf5BIyX0rhnM/1oKYjP+X7ROwun99DkOKouaxD05RzHqvW8ym
ykr+ffNFdd8Ev0NPGIt7GFKKP3xfx+DEILCvhaGEBWiw19IPHMeCGQScJEH2rF36////Kf+/f/+eDG
QsXcv4f+p1gRfZhkDzz0+V+KCZzQAUfv8fCr4DMcQdSAAA+dJRILrFW04AAAAASUVORK5CYII='''

CAPTION_IMAGE_STYLE = '''\
    <style type="text/css">
        span { display:inline-table; }
        p { margin-top:0px; margin-bottom:0px; }
     </style>\
'''

START = f'''\
<html>

<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>%s</title>
    <link rel="icon" href="data:image/png;base64,\n{FAVICON_BASE64}" />
{CAPTION_IMAGE_STYLE}
    <meta name="viewport" content="width=device-width">
    <link rel="stylesheet" href="photobox/photobox.css">
    <script src="photobox/jquery.min.js"></script>
    <script src="photobox/jquery.photobox.js"></script>
</head>

<body>\
'''

GALLERYCALL = "$('#%s').photobox('a', { thumbs:true, time:0, history:false, loop:false });"

END = '</body>\n</html>'
SEP = '<hr color="#C0C0C0" size="1" />'
IMGPOST = '<a href="%s"><img src="%s" width="400" title="%s"/></a>'
IMGPOSTCAPTION = '''\
<span>
<a href="%s"><img src=%s width="400" title="%s"/></a>
<p>%s</p>
</span>
'''
IMGDCIM = '<a href="file:///%s"><img src="%s" width="300" title="%s"/></a>'
VIDPAT2 = '<a href="file:///%s" rel="video"><img src="%s" width="300" title="%s"/></a>'

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


class PostImage:
    def __init__(self, caption, uri, creation, thumb=None, descr=''):
        self.caption = caption
        self.uri = uri
        self.basename = os.path.basename(uri)
        self.creation = creation
        self.thumb = thumb
        self.descr = descr
        self.resized_url = None

    def to_html_post(self):
        if not self.caption:
            return IMGPOST % (self.uri, self.thumb, self.descr)
        else:
            return IMGPOSTCAPTION % (self.uri, self.thumb, self.descr, self.caption)

    def to_html_dcim(self):
        return IMGDCIM % (self.uri, self.thumb, self.descr)

    def to_html_blogger(self):
        if not self.caption:
            return BIMGPAT % (self.uri, self.resized_url)
        else:
            return f'{BIMGPAT}\n{CAPTION_PAT}' % (self.uri, self.resized_url, self.caption)


class PostVideo(PostImage):
    def to_html_post(self):
        return VIDPAT2 % (self.uri, '', '')

    def to_html_dcim(self):
        return VIDPAT2 % (self.uri, self.thumb, self.descr)


class Post:
    def __init__(self, timestamp, title, text, photos):
        self.timestamp = timestamp
        self.title = title
        self.text = text
        self.images = photos
        self.dcim = []
        self.date = None
        self.daterank = 0

    def __lt__(self, other):
        return self.date < other.date

    @classmethod
    def from_markdown(cls, md_post):
        timestamp = None  # pour le moment
        post = ''.join(md_post)

        m = re.match(r'\[([0-9/]{10})\]\n*', post)
        if m:
            date = m.group(1).replace('/', '-')
            post = post[m.end():]
        else:
            error(f'No date in record {md_post}')

        m = re.match(r'###### *([^\n]+)\n*', post)
        if m:
            title = m.group(1)
            post = post[m.end():]
        else:
            title = None

        text = list()
        while m := re.match(r'(?!\!?\[\])(([^\n]+\n)+)(\n|$)', post):
            para = m.group(1).replace('\n', ' ')
            text.append(para)
            post = post[m.end():]

        if m := re.match(r'(\n+)', post):
            post = post[m.end():]

        images = list()
        while m := re.match(r'!?\[\]\(([^\n]+)\)\n(([^![][^\n]+)\n)?', post):
            if m.group(0)[0] == '!':
                images.append(PostImage(group(m, 3), m.group(1), None))
            else:
                images.append(PostVideo(group(m, 3), m.group(1), None))
            post = post[m.end():]

        post = cls(timestamp, title, text, images)
        post.date = date
        return post

    def to_html(self, target='local'):
        if target == 'local':
            return self.to_html_local()
        if target == 'blogger':
            return self.to_html_blogger()

    def to_html_local(self):
        html = list()
        ##print(markdown.markdown(self.text)) TODO: remove
        html.append(SEP)
        if self.title:
            html.append(f'<b>{self.title}</b>')
            html.append('<br />')
        text = [md_links_to_html(line) for line in self.text]
        if text:
            line = text[0]
            html.append(line)
            for line in text[1:]:
                html.append(f'<br />{line}')
            html.append('<br />')

        if self.images:
            html.append(f'<div id="gallery-{self.date}-blog-{self.daterank}">')
            for media in self.images:
                html.append(media.to_html_post())
            html.append('</div>')

        if self.dcim:
            html.append(SEP)
            html.append(f'<div id="gallery-{self.date}-dcim-{self.daterank}">')
            for media in self.dcim:
                html.append(media.to_html_dcim())
            html.append('</div>')

        return html

    def to_html_blogger(self):
        html = list()
        html.append(SEP)
        if self.title:
            html.append(f'<b>{self.title}</b>')
            html.append('<br />')
        text = [md_links_to_html(line) for line in self.text]
        if text:
            line = text[0]
            html.append(line)
            for line in text[1:]:
                html.append(f'<br />{line}')
            html.append('<br />')
        for image in self.images:
            html.append(image.to_html_blogger())
        return html


def md_links_to_html(line):
    line = html.escape(line, quote=False)
    line = re.sub(r'(?<!\!)\[([^]]*)\]\(([^)]*)\)', r'<a href=\2>\1</a>', line)
    return line


def group(match, n):
    try:
        return match.group(n)
    except:
        return None


# -- Markdown parser ----------------------------------------------------------


def parse_markdown(filename):
    """
    Generate Post objects from markdown. Posts are in chronological order.
    """
    title = None
    posts = list()
    if not os.path.exists(filename):
        print('/!\\', 'File not found:', filename)
    else:
        with open(filename, encoding='utf-8') as f:
            line = next(f)
            if line.startswith('# '):
                title = line[2:].strip()
                record = []
                next(f)
            else:
                title = None
                record = [line]
            for line in f:
                if '___' not in line:
                    record.append(line)
                else:
                    posts.append(Post.from_markdown(record))
                    record = []

        daterank = defaultdict(int)
        for post in posts:
            daterank[post.date] += 1
            post.daterank = daterank[post.date]

    return title, posts


# -- Markdown printer ---------------------------------------------------------

def print_markdown(posts, title, fullname):
    with open(fullname, 'wt', encoding='utf-8') as fdst:
        print(f'# {title}\n', file=fdst)
        for post in posts:
            print(f"[{post.date.replace('-', '/')}]", file=fdst)
            print(file=fdst)
            if post.title:
                print(f'###### {post.title}', file=fdst)
                print(file=fdst)
            for line in post.text:
                for chunk in textwrap.wrap(line, width=78):
                    print(chunk, file=fdst)
            print(file=fdst)
            for media in post.images:
                print(f'![]({media.uri})', file=fdst)
                if media.caption:
                    print(media.caption, file=fdst)
            print('______', file=fdst)


# -- html printer -------------------------------------------------------------


def compose_html(posts, title, target):
    html = list()
    html.append(START % title)

    for post in posts:
        for line in post.to_html(target):
            html.append(line.strip())
        html.append('')

    html.append('<script>')
    for post in posts:
        if post.images:
            html.append(f"$('#gallery-{post.date}-blog').photobox('a', {{ thumbs:true, time:0, history:false, loop:false }});")
    html.append('</script>')

    html.append(END)
    return html


def compose_html_extended(posts, title, target):
    html = list()
    html.append(START % title)

    for post in posts:
        for line in post.to_html(target):
            html.append(line.strip())
        html.append('')

    html.append('<script>')
    for post in posts:
        if post.images:
            html.append(GALLERYCALL % f'gallery-{post.date}-blog-{post.daterank}')
        if post.dcim:
            html.append(GALLERYCALL % f'gallery-{post.date}-dcim-{post.daterank}')
    html.append('</script>')

    html.append(END)
    return html


def print_html_to_stream(posts, title, stream, target):
    if target == 'extended':
        for line in compose_html_extended(posts, title, 'local'):
            print(line, file=stream)
    else:
        for line in compose_html(posts, title, target):
            print(line, file=stream)


def print_html(posts, title, html_name, target='local'):
    assert target in ('local', 'extended', 'blogger')
    if html_name:
        with open(html_name, 'wt', encoding='utf-8') as f:
            print_html_to_stream(posts, title, f, target)
            return None
    else:
        with io.StringIO() as f:
            print_html_to_stream(posts, title, f, target)
            return f.getvalue()


# -- Media description --------------------------------------------------------


def date_from_name(name):
    # heuristics
    if match := re.search(r'(?:[^0-9]|^)(\d{8})([^0-9]|$)', name):
        digits = match.group(1)
        year, month, day = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
        if 2000 <= year <= date.today().year and 1 <= month <= 12 and 1 <= day <= 31:
            return digits
        else:
            return None
    else:
        return None


def date_from_item(filename):
    if date := date_from_name(filename):
        return date
    else:
        timestamp = os.path.getmtime(filename)
        return datetime.fromtimestamp(timestamp).strftime('%Y%m%d')


def time_from_name(name):
    # heuristics
    if match := re.search(r'(?:[^0-9]|^)(\d{8})[^0-9](\d{6})([^0-9]|$)', name):
        digits = match.group(2)
        hour, minute, second = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])
        if 0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60:
            return digits
        else:
            return None
    else:
        return None


def time_from_item(filename):
    if time := time_from_name(filename):
        return time
    else:
        timestamp = os.path.getmtime(filename)
        return datetime.fromtimestamp(timestamp).strftime('%H%M%S')


COMMAND = '''\
    ffprobe -v error
            -select_streams v:0
            -show_entries stream=width,height,avg_frame_rate,r_frame_rate:format=duration
            -of csv=p=0
'''


def get_image_info(filename):
    date = date_from_item(filename)
    time = time_from_item(filename)
    img = Image.open(filename)
    width, height = img.size
    size = round(os.path.getsize(filename) / 1e6, 1)
    return (date, time, width, height, size), f'{date} {time}, dim={width}x{height}, {size} MB'


def get_video_info(filename):
    # ffmpeg must be in path
    date = date_from_item(filename)
    time = time_from_item(filename)
    command = [*COMMAND.split(), filename]
    try:
        output = check_output(command, stderr=STDOUT).decode()
        match = re.match(r'(\d+),(\d+),(\d+)/(\d+),(\d+)/(\d+)\s*(\d+\.\d+)', output)
        width = match.group(1)
        height = match.group(2)
        fps = round(int(match.group(3)) / int(match.group(4)), 1)
        duration = round(float(match.group(7)))
        size = round(os.path.getsize(filename) / 1e6, 1)
        output = f'{date} {time}, dim={width}x{height}, m:s={duration // 60:02}:{duration % 60:02}, fps={fps}, {size} MB'
    except CalledProcessError as e:
        output = e.output.decode()
    return (date, time, width, height, size, duration, fps), output


# -- Thumbnails (image and video) ---------------------------------------------


def make_thumbnail(image_name, thumb_name, size):
    if os.path.exists(thumb_name):
        pass
    else:
        print('Making thumbnail:', thumb_name)
        create_thumbnail(image_name, thumb_name, size)


def create_thumbnail(image_name, thumb_name, size):
    imgobj = Image.open(image_name)

    # fix for downscaled images and some GIFs per above [1.7]
    if (imgobj.mode != 'RGBA' and image_name.endswith('jpg')
                              and not (image_name.endswith('gif') and imgobj.info.get('transparency'))):
        imgobj = imgobj.convert('RGBA')

    if hasattr(Image, 'LANCZOS'):                 # best downsize filter [2018]
        imgobj.thumbnail(size, Image.LANCZOS)     # but newer Pillows only
    else:
        imgobj.thumbnail(size, Image.ANTIALIAS)   # original filter

    imgobj = imgobj.convert('RGB')
    imgobj.save(thumb_name)


def make_thumbnail_video(video_name, thumb_name, size):
    if os.path.exists(thumb_name):
        pass
    else:
        print('Making thumbnail:', thumb_name)
        create_thumbnail_video(video_name, thumb_name, size)


# base64 video.png
VIDEO_ICON = '''\
iVBORw0KGgoAAAANSUhEUgAAABgAAAAUCAAAAACy3qJfAAAA4UlEQVR4
2m1QoRbCMAy88SaK69xscfuEWiS4SZBIcCCRfAL8An8AcnJzTOJSWdxwzJXSPUoHRPQlueYuucigxm
9kDGaMf8AjopGcYn8LmmyLoihBWBiThb+5MTuUsc3aL56upneZ9sByAIg8Z8BEn96EeZ65iU7DvmbP
PxqDcH6p1swXBC4l6yZskACkTN1WrQr2SlIFhTtgqeZa+zsOogLXegvEocZ5c/W5BcoVNNCg3hSudV
/hEh4ofw6cEb00Km8i0dpRDUXfKiaQOEAdrUDo4dFp9C33jjaRac9/gDF/AlplVYtfWGCjAAAAAElF
TkSuQmCC'''


def create_thumbnail_video(filename, thumbname, size):
    # ffmpeg must be in path
    sizearg = '%dx%d' % size
    command = 'ffmpeg -v error -i "%s" -vcodec mjpeg -vframes 1 -an -f rawvideo -s %s "%s"'
    command = command % (filename, sizearg, thumbname)
    result = os.system(command)

    # add a movie icon to the thumbnail to identify videos
    img1 = Image.open(thumbname)
    img2 = Image.open(io.BytesIO(base64.b64decode(VIDEO_ICON)))
    width, height = img1.size
    img1.paste(img2, (6, height - 20 - 6), None)
    img1.save(thumbname)


def create_item(media_fullname, thumbdir, key):
    media_basename = os.path.basename(media_fullname)
    if media_basename.lower().endswith('.jpg'):
        thumb_basename = key + '-' + media_basename
        thumb_fullname = os.path.join(thumbdir, thumb_basename)
        try:
            info, infofmt = get_image_info(media_fullname)
            infofmt = media_basename + ': ' + infofmt
            make_thumbnail(media_fullname, thumb_fullname, (300, 300))
            item = PostImage(None, media_fullname, None, '/'.join(('.thumbnails', thumb_basename)), infofmt)
        except PIL.UnidentifiedImageError:
            # corrupted image
            warning(f'** Unable to read image {media_fullname}')
            return None, ''
    else:
        thumb_basename = key + '-' + media_basename.replace('.mp4', '.jpg')
        thumb_fullname = os.path.join(thumbdir, thumb_basename)
        info, infofmt = get_video_info(media_fullname)
        infofmt = media_basename + ': ' + infofmt
        thumbheight = int(round(300 * int(info[3]) / int(info[2])))
        make_thumbnail_video(media_fullname, thumb_fullname, (300, thumbheight))
        item = PostVideo(None, media_fullname, None, '/'.join(('.thumbnails', thumb_basename)), infofmt)
    return item, thumb_fullname


# -- Markdown format ----------------------------------------------------------


def create_index(args):
    # list of all pictures and movies
    medias = list_of_medias(args.imgsource, args.recursive)

    # list of required dates (the DCIM directory can contain images not related
    # with the desired index (e.g. two indexes for the same image directory)
    required_dates = set()
    if args.dates:
        date1, date2 = args.dates.split('-')
        for media in medias:
            date = date_from_item(media)
            if date1 <= date <= date2:
                required_dates.add(date)
    else:
        for media in medias:
            date = date_from_item(media)
            required_dates.add(date)

    title = args.imgsource
    posts = list()
    for date in sorted(required_dates):
        year, month, day = date[0:4], date[4:6], date[6:8]
        x = datetime(int(year), int(month), int(day))
        datetext = x.strftime("%A %d %B %Y").capitalize()
        post = Post(None, title=datetext, text=[], photos=[])
        post.date = f'{year}-{month}-{day}'
        posts.append(post)

    os.makedirs(args.output, exist_ok=True)
    print_markdown(posts, title, os.path.join(args.output, 'index.md'))


def make_basic_index(args):
    # check for ffmpeg and ffprobe in path
    for exe in ('ffmpeg', 'ffprobe'):
        try:
            check_output([exe, '-version'])
        except FileNotFoundError:
            error(f'File not found: {exe}')

    thumbdir = os.path.join(args.input, '.thumbnails')
    if not os.path.exists(thumbdir):
        os.mkdir(thumbdir)

    photoboxdir = os.path.join(args.input, 'photobox')
    if not os.path.exists(photoboxdir):
        photoboxsrc = os.path.join(os.path.dirname(__file__), 'photobox')
        shutil.copytree(photoboxsrc, photoboxdir)

    if os.path.exists(os.path.join(args.input, 'index.md')):
        title, posts = parse_markdown(os.path.join(args.input, 'index.md'))
    else:
        title = os.path.basename(args.input)
        posts = list()

    for post in posts:
        for media in post.images:
            media_fullname = os.path.join(args.input, media.uri)
            item, _ = create_item(media_fullname, thumbdir, 'post')
            media.thumb = '/'.join(('.thumbnails', os.path.basename(item.thumb)))
            media.descr = item.descr

    thumblist = []
    for post in posts:
        thumblist.extend([os.path.basename(media.thumb) for media in post.images])
    purge_thumbnails(thumbdir, thumblist, 'post')

    return title, posts


def purge_thumbnails(thumbdir, thumblist, key):
    # purge thumbnail dir from irrelevant thumbnails (e.g. after renaming images)
    for fullname in glob.glob(os.path.join(thumbdir, f'{key}*.jpg')):
        if os.path.basename(fullname) not in thumblist:
            print('Removing thumbnail', fullname)
            os.remove(fullname)


def markdown_to_html(args):
    title, posts = make_basic_index(args)
    print_html(posts, title, os.path.join(args.input, 'index.htm'), 'extended')


# -- Addition of DCIM images --------------------------------------------------


def extend_index(args):
    title, posts = make_basic_index(args)

    # list of all pictures and movies
    medias = list_of_medias(args.imgsource, args.recursive)

    # list of required dates (the DCIM directory can contain images not related
    # with the current page (e.g. two pages for the same image directory)
    if args.dates:
        date1, date2 = args.dates.split('-')
        required_dates = set()
        for media in medias:
            date = date_from_item(media)
            if date1 <= date <= date2:
                required_dates.add(date)
    else:
        required_dates = set()
        for post in posts:
            if post.date:
                date = post.date
                date = date.replace('-', '')
                required_dates.add(date)

    bydate = defaultdict(list)
    thumbnails = list()
    thumbdir = os.path.join(args.input, '.thumbnails')
    for media_fullname in medias:
        date = date_from_item(media_fullname)  #  calculé deux fois
        if date in required_dates:
            item, thumb_fullname = create_item(media_fullname, thumbdir, 'dcim')
            if item:
                bydate[date].append(item)
                thumbnails.append(thumb_fullname)

    for date, liste in bydate.items():
        liste.sort(key=lambda item: time_from_item(item.uri))

    # make list of extra dates (not in posts)
    extradates = required_dates - {post.date.replace('-', '') for post in posts}

    # complete posts with extra dates from args.dates
    for date in extradates:
        timestamp = time.mktime(time.strptime(date, '%Y%m%d'))
        year, month, day = date[0:4], date[4:6], date[6:8]
        x = datetime(int(year), int(month), int(day))
        datetext = x.strftime("%A %d %B %Y").capitalize()
        newpost = Post(timestamp, title=None, text=[datetext], photos=[])
        newpost.date = f'{year}-{month}-{day}'
        newpost.daterank = 1
        newpost.dcim = bydate[date]  # TODO: refait en dessous
        bisect.insort(posts, newpost)

    # several posts can have the same date, only the first one is completed with dcim images
    for post in posts:
        if post.daterank == 1:
            date = post.date
            date = date.replace('-', '')
            post.dcim = bydate[date]

    thumblist = []
    for post in posts:
        thumblist.extend([os.path.basename(media.thumb) for media in post.dcim])
    purge_thumbnails(thumbdir, thumblist, 'dcim')

    print_html(posts, title, os.path.join(args.input, 'index-x.htm'), 'extended')


def list_of_files(sourcedir, recursive):
    """ return the list of full paths for files in source directory
    """
    result = list()
    if recursive is False:
        for basename in os.listdir(sourcedir):
            result.append(os.path.join(sourcedir, basename))
    else:
        for root, dirs, files in os.walk(sourcedir):
            for basename in files:
                result.append(os.path.join(root, basename))
    return result


def list_of_medias(imgsource, recursive):
    """ return the list of full paths for pictures and movies in source directory
    """
    files = list_of_files(imgsource, recursive)
    return [_ for _ in files if os.path.splitext(_)[1].lower() in ('.jpg', '.mp4')]


# -- Export to blogger---------------------------------------------------------


def online_images_url(args):
    with urlopen(args.urlblogger) as u:
        buffer = u.read()
        buffer = buffer.decode('utf-8')

    online_images = dict()
    for match in re.finditer('<div class="separator".*?</div>', buffer, flags=re.DOTALL):
        div_separator = match.group(0)
        elem_div = objectify.fromstring(div_separator)
        for elem_a in elem_div.iterchildren(tag='a'):
            href = elem_a.get("href")
            thumb = elem_a.img.get("src")
            online_images[os.path.basename(href)] = (href, thumb)

    return online_images


def compare_image_buffers(imgbuf1, imgbuf2):
    with io.BytesIO(imgbuf1) as imgio1, io.BytesIO(imgbuf2) as imgio2:
        img1 = Image.open(imgio1)
        img2 = Image.open(imgio2)
        diff = ImageChops.difference(img1, img2)
        return not diff.getbbox()


def check_images(args, posts, online_images):
    result = True
    for post in posts:
        for image in post.images:
            if image.basename in online_images:
                with open(os.path.join(args.input, image.uri), 'rb') as f:
                    imgbuf1 = f.read()
                try:
                    with urlopen(online_images[image.basename][0]) as u:
                        imgbuf2 = u.read()
                except FileNotFoundError:
                    print('File not found', online_images[image.basename][0])
                    next
                if compare_image_buffers(imgbuf1, imgbuf2) is False:
                    print('Files are different, upload', image.basename)
                else:
                    if 1:
                        print('File already online', image.basename)
            else:
                print('File is absent, upload', image.basename)
                result = False
    return result


def compose_blogger_html(args, title, posts, imgdata):
    """ Compose html with blogger image urls
    """
    for post in posts:
        for image in post.images:
            if image.uri not in imgdata:
                print('Image missing: ', image.uri)
            else:
                img_url, resized_url = imgdata[image.uri]
                image.uri = img_url
                image.resized_url = resized_url

    return print_html(posts, title, '', target='blogger').splitlines()


def prepare_for_blogger(args):
    """
    Export blogger html to clipboard.
    If --full, export complete html, otherwise export html extract ready to
    paste into blogger edit mode.
    """
    title, posts = parse_markdown(os.path.join(args.input, 'index.md'))
    online_images = online_images_url(args)

    if args.check_images and check_images(args, posts, online_images) is False:
        pass

    html = compose_blogger_html(args, title, posts, online_images)
    html = '\n'.join(html)

    if args.full is False:
        html = re.search('<body>(.*)?</body>', html, flags=re.DOTALL).group(1)
        html = re.sub('<script>.*?</script>', '', html, flags=re.DOTALL)

    clipboard.copy(html)


# -- Other commands -----------------------------------------------------------


def rename_images(posts, path):
    for post in posts:
        for image in post.images:
            try:
                seqname = post.date + '-' + post.daterank + os.path.splitext(image.uri)[1]
                os.rename(os.path.join(path, image.uri), os.path.join(path, seqname))
                image.uri = image.seqname
            except IOError:
                print('Unable to rename:', os.path.join(path, image.uri), '-->', os.path.join(path, seqname))


def rename_images_cmd(args):
    posts = parse_markdown(os.path.join(args.input, 'index.md'))
    rename_images(posts, args.input)
    print_html(posts, 'TITLE', os.path.join(args.input, 'index.htm'))


def idempotence(args):
    title, posts = parse_markdown(os.path.join(args.input, 'index.md'))
    print_markdown(posts, title, os.path.join(args.output, 'index.md'))


# -- Main ---------------------------------------------------------------------


def parse_command_line():
    parser = argparse.ArgumentParser(description=None, usage=USAGE)

    parser.add_argument('--create', help='create journal from medias in --imgsource',
                        action='store_true', default=False)
    parser.add_argument('--html', help='input md, output html',
                        action='store_true', default=False)
    parser.add_argument('--extend', help='extend image set, source in --imgsource',
                        action='store_true', default=False)
    parser.add_argument('--blogger', dest='blogger',
                        help='input md, html blogger ready in clipboard',
                        action='store_true', default=False)
    parser.add_argument('--rename_img', help='fix photo names renaming as date+index',
                        action='store_true', default=None)

    parser.add_argument('--idem', help='',
                        action='store_true', default=False)
    parser.add_argument('--test', help='',
                        action='store_true', default=False)

    parser.add_argument('-i', '--input', help='input parameter',
                        action='store', default=None)
    parser.add_argument('-o', '--output', help='output parameter',
                        action='store', default=None)
    parser.add_argument('--year', help='year',
                        action='store', default=None)
    parser.add_argument('--dates', help='dates interval for extended index',
                        action='store', default=None)
    parser.add_argument('--imgsource', help='image source for extended index',
                        action='store', default=None)
    parser.add_argument('--recursive', help='--imgsource scans recursively',
                        action='store_true', default=True)
    parser.add_argument('--flat', dest='recursive', help='--imgsource does not recurse',
                        action='store_false')

    parser.add_argument('--full', help='full html (versus blogger ready html)',
                        action='store_true', default=False)
    parser.add_argument('--check', dest='check_images', help='check availability of images on blogger',
                        action='store_true')
    parser.add_argument('--url', dest='urlblogger', help='blogger post url',
                        action='store')
    args = parser.parse_args()

   # check and normalize paths
    if args.input:
        args.input = os.path.abspath(args.input)
        if not os.path.isdir(args.input):
            error(f'** Directory not found: {args.input}')
    if args.output:
        args.output = os.path.abspath(args.output)
    if args.imgsource:
        args.imgsource = os.path.abspath(args.imgsource)
        if not os.path.isdir(args.imgsource):
            error(f'** Directory not found: {args.imgsource}')
    if args.blogger and args.urlblogger is None:
        error(f'** Give blogger url with --url')

    return args


def warning(msg):
    print(msg)


def error(msg):
    print(msg)
    sys.exit(1)


def main():
    locale.setlocale(locale.LC_TIME, '')
    args = parse_command_line()

    if args.create:
        create_index(args)

    elif args.html:
        markdown_to_html(args)

    elif args.extend:
        extend_index(args)

    elif args.rename_img:
        rename_images_cmd(args)

    elif args.blogger:
        prepare_for_blogger(args)

    elif args.idem:
        idempotence(args)

    elif args.test:
        pass


if __name__ == '__main__':
    main()
