"""
Media directory and diary organizer. Handle a markdown file organized by dates,
each day described by a text and a subset of the medias (photos and movies).

The markdown file can be:
* edited manually (very basic syntax),
* created from the media directory.

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
import bisect
import locale
import textwrap
import base64
import datetime
from collections import defaultdict
from subprocess import check_output, CalledProcessError, STDOUT
from urllib.request import urlopen

import clipboard
import PIL
from PIL import Image, ImageChops
from lxml import objectify
import markdown


USAGE = """
journal --create  <root-dir> --imgsource <media-dir> [--dates <yyyymmdd-yyyymmdd>]
journal --html    <root-dir> [--dest <dir>]
journal --extend  <root-dir> --imgsource <media-dir> [--dates <yyyymmdd-yyyymmdd>] [--dest <dir>]
journal --blogger <root-dir> --url <url> [--check] [--full]
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
 </style>\
'''

STYLE = '''\
<style type="text/css">
    p { margin-top:0px; margin-bottom:0px; }
    h3 { font-size: 100%%; font-weight: bold; margin-top:0px; margin-bottom:0px; }
 </style>
'''

START = f'''\
<html>

<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>%s</title>
    <link rel="icon" href="data:image/png;base64,\n{FAVICON_BASE64}" />
    <meta name="viewport" content="width=device-width">
    <link rel="stylesheet" href="photobox/photobox.css">
    <script src="photobox/jquery.min.js"></script>
    <script src="photobox/jquery.photobox.js"></script>
{CAPTION_IMAGE_STYLE}
{STYLE}
</head>

<body>\
'''

GALLERYCALL = "$('#%s').photobox('a', { thumbs:true, time:0, history:false, loop:false });"

END = '</body>\n</html>'
SEP = '<hr color="#C0C0C0" size="1" />'
IMGPOST = '<a href="%s"><img src="%s" width="%d" height="%d" title="%s"/></a>'
VIDPOST = '<a href="%s" rel="video"><img src="%s" width="%d" height="%d" title="%s"/></a>'
IMGPOSTCAPTION = '''\
<span>
<a href="%s"><img src=%s width="%d" height="%d" title="%s"/></a>
<p>%s</p>
</span>
'''
VIDPOSTCAPTION = '''\
<span>
<a href="%s" rel="video"><img src=%s width="%d" height="%d" title="%s"/></a>
<p>%s</p>
</span>
'''
IMGDCIM = '<a href="file:///%s"><img src="%s" width="%d" height="%d" title="%s"/></a>'
VIDDCIM = '<a href="file:///%s" rel="video"><img src="%s" width="%d" height="%d" title="%s"/></a>'

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


class Post:
    def __init__(self, date, text, medias):
        # date: yyyymmdd
        self.date = date
        self.text = text
        self.medias = medias
        self.dcim = []
        self.daterank = 0

    def __lt__(self, other):
        return self.date < other.date

    @classmethod
    def from_markdown(cls, post):
        m = re.match(r'\[([0-9/]{10})\]\n*', post[0])
        if m:
            date = m.group(1).replace('/', '')
            del post[0]
        else:
            error('No date in record', post)

        while post and not post[0].strip():
            del post[0]

        text = ''
        while post and not re.match(r'!?\[\]', post[0]):
            text += post[0]
            del post[0]

        # remove empty lines at end
        text = re.sub(r'\n\n$', '\n', text)

        medias = list()
        while post and (match := re.match(r'!?\[\]\((.*)\)', post[0])):
            media = match.group(1)
            caption = None
            del post[0]
            if post and not re.match(r'!?\[\]', post[0]):
                caption = post[0].strip()
                del post[0]
            if match.group(0)[0] == '!':
                medias.append(PostImage(caption, media))
            else:
                medias.append(PostVideo(caption, media))

        return cls(date, text, medias)

    @classmethod
    def from_date(cls, date):
        dt = datetime.datetime.strptime(date, '%Y%m%d')
        datetext = dt.strftime("%A %d %B %Y").capitalize()
        post = cls(date, text=datetext, medias=[])
        post.daterank = 1
        return post

    def to_html(self, target='regular'):
        if target == 'regular':
            return self.to_html_regular()
        if target == 'blogger':
            return self.to_html_blogger()

    def to_html_regular(self):
        html = list()
        if self.text:
            html.append(markdown.markdown(self.text))

        if self.medias:
            html.append(f'<div id="gallery-{self.date}-blog-{self.daterank}">')
            for media in self.medias:
                html.append(media.to_html_post())
            html.append('</div>')

        if self.dcim:
            html.append(SEP)
            html.append(f'<div id="gallery-{self.date}-dcim-{self.daterank}">')
            for media in self.dcim:
                html.append(media.to_html_dcim())
            html.append('</div>')

        html.append(SEP)
        return html

    def to_html_blogger(self):
        html = list()
        html.append(markdown.markdown(self.text))
        for image in self.medias:
            html.append(image.to_html_blogger())
        html.append(SEP)
        return html


class PostItem:
    def __init__(self, caption, uri, thumb=None, thumbsize=None, descr=''):
        self.caption = caption
        self.uri = uri
        self.basename = os.path.basename(uri)
        self.thumb = thumb
        self.thumbsize = thumbsize
        self.descr = descr
        self.resized_url = None


class PostImage(PostItem):
    def to_markdown(self):
        if not self.caption:
            return '![](%s)' % (self.uri,)
        else:
            return '![](%s)\n%s' % (self.uri, self.caption)

    def to_html_post(self):
        if not self.caption:
            return IMGPOST % (self.uri, self.thumb, *self.thumbsize, self.descr)
        else:
            return IMGPOSTCAPTION % (self.uri, self.thumb, *self.thumbsize, self.descr, self.caption)

    def to_html_dcim(self):
        return IMGDCIM % (self.uri, self.thumb, *self.thumbsize, self.descr)

    def to_html_blogger(self):
        if not self.caption:
            return BIMGPAT % (self.uri, self.resized_url)
        else:
            return f'{BIMGPAT}\n{CAPTION_PAT}' % (self.uri, self.resized_url, self.caption)


class PostVideo(PostItem):
    def to_markdown(self):
        if not self.caption:
            return '[](%s)' % (self.uri,)
        else:
            return '[](%s)\n%s' % (self.uri, self.caption)

    def to_html_post(self):
        if not self.caption:
            return VIDPOST % (self.uri, self.thumb, *self.thumbsize, self.descr)
        else:
            return VIDPOSTCAPTION % (self.uri, self.thumb, *self.thumbsize, self.descr, self.caption)

    def to_html_dcim(self):
        return VIDDCIM % (self.uri, self.thumb, *self.thumbsize, self.descr)

    def to_html_blogger(self):
        x = f'<p style="text-align: center;">{self.iframe}</p>'
        if not self.caption:
            return x
        else:
            return f'%s\n{CAPTION_PAT}' % (x, self.caption)


# -- Markdown parser ----------------------------------------------------------


def parse_markdown(filename):
    """
    Generate Post objects from markdown. Date must be present in each post and
    posts must be ordrered by date.
    """
    if not os.path.exists(filename):
        error('File not found', filename)

    posts = list()
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

    # set rank of posts in date
    daterank = defaultdict(int)
    for post in posts:
        daterank[post.date] += 1
        post.daterank = daterank[post.date]

    # check post order
    for post1, post2 in zip(posts[:-1], posts[1:]):
        if post1.date > post2.date:
            error('Posts are not ordered', f'{post1.date} > {post2.date}')

    return title, posts


# -- Markdown printer ---------------------------------------------------------

def print_markdown(posts, title, fullname):
    with open(fullname, 'wt', encoding='utf-8') as fdst:
        print(f'# {title}\n', file=fdst)
        for post in posts:
            date = f'[{post.date[0:4]}/{post.date[4:6]}/{post.date[6:8]}]'
            print(date, file=fdst)
            if post.text:
                print(file=fdst)
                for line in post.text.splitlines():
                    if not line:
                        print(file=fdst)
                    else:
                        for chunk in textwrap.wrap(line, width=78):
                            print(chunk, file=fdst)
            if post.medias:
                print(file=fdst)
                for media in post.medias:
                    print(media.to_markdown(), file=fdst)
            print('______', file=fdst)


# -- html printer -------------------------------------------------------------


def compose_html_reduced(posts, title, target):
    html = list()
    html.append(START % title)

    for post in posts:
        for line in post.to_html(target):
            html.append(line.strip())
        html.append('')

    html.append(END)
    return html


def compose_html_full(posts, title, target):
    html = list()
    html.append(START % title)

    for post in posts:
        for line in post.to_html(target):
            html.append(line.strip())
        html.append('')

    html.append('<script>')
    for post in posts:
        if post.medias:
            html.append(GALLERYCALL % f'gallery-{post.date}-blog-{post.daterank}')
        if post.dcim:
            html.append(GALLERYCALL % f'gallery-{post.date}-dcim-{post.daterank}')
    html.append('</script>')

    html.append(END)
    return html


def print_html_to_stream(posts, title, stream, target):
    if target == 'regular':
        for line in compose_html_full(posts, title, target):
            print(line, file=stream)
    else:
        for line in compose_html_reduced(posts, title, target):
            print(line, file=stream)


def print_html(posts, title, html_name, target='regular'):
    assert target in ('regular', 'blogger')
    if html_name:
        with open(html_name, 'wt', encoding='utf-8') as f:
            print_html_to_stream(posts, title, f, target)
            return None
    else:
        with io.StringIO() as f:
            print_html_to_stream(posts, title, f, target)
            return f.getvalue()


# -- Media description --------------------------------------------------------


def is_media(name):
    return os.path.splitext(name)[1].lower() in ('.jpg', '.mp4')


def date_from_name(name):
    # heuristics
    if match := re.search(r'(?:[^0-9]|^)(\d{8})([^0-9]|$)', name):
        digits = match.group(1)
        year, month, day = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
        if 2000 <= year <= datetime.date.today().year and 1 <= month <= 12 and 1 <= day <= 31:
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
        return datetime.datetime.fromtimestamp(timestamp).strftime('%Y%m%d')


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
        return datetime.datetime.fromtimestamp(timestamp).strftime('%H%M%S')


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
        width = int(match.group(1))
        height = int(match.group(2))
        fps = round(int(match.group(3)) / int(match.group(4)), 1)
        duration = round(float(match.group(7)))
        size = round(os.path.getsize(filename) / 1e6, 1)
        mn = duration // 60
        sec = duration % 60
        output = f'{date} {time}, dim={width}x{height}, m:s={mn:02}:{sec:02}, fps={fps}, {size} MB'
    except CalledProcessError as e:
        output = e.output.decode()
    return (date, time, width, height, size, duration, fps), output


# -- Thumbnails (image and video) ---------------------------------------------


def size_thumbnail(width, height, maxdim):
    if width >= height:
        return maxdim, int(round(maxdim * height / width))
    else:
        return int(round(maxdim * width / height)), maxdim


def make_thumbnail(image_name, thumb_name, size):
    if os.path.exists(thumb_name):
        pass
    else:
        print('Making thumbnail:', thumb_name)
        create_thumbnail(image_name, thumb_name, size)


def create_thumbnail(image_name, thumb_name, size):
    imgobj = Image.open(image_name)

    if (imgobj.mode != 'RGBA'
        and image_name.endswith('.jpg')
        and not (image_name.endswith('.gif') and imgobj.info.get('transparency'))
       ):
        imgobj = imgobj.convert('RGBA')

    imgobj.thumbnail(size, Image.LANCZOS)
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


def create_item(media_fullname, thumbdir, key, thumbmax):
    media_basename = os.path.basename(media_fullname)
    if media_basename.lower().endswith('.jpg'):
        thumb_basename = key + '-' + media_basename
        thumb_fullname = os.path.join(thumbdir, thumb_basename)
        try:
            info, infofmt = get_image_info(media_fullname)
            infofmt = media_basename + ': ' + infofmt
            thumbsize = size_thumbnail(info[2], info[3], thumbmax)
            make_thumbnail(media_fullname, thumb_fullname, thumbsize)
            item = PostImage(None, media_fullname, '/'.join(('.thumbnails', thumb_basename)),
                            thumbsize, infofmt)
        except PIL.UnidentifiedImageError:
            # corrupted image
            warning(f'** Unable to read image {media_fullname}')
            return None, ''
    else:
        thumb_basename = key + '-' + media_basename.replace('.mp4', '.jpg')
        thumb_fullname = os.path.join(thumbdir, thumb_basename)
        info, infofmt = get_video_info(media_fullname)
        infofmt = media_basename + ': ' + infofmt
        thumbsize = size_thumbnail(info[2], info[3], thumbmax)
        make_thumbnail_video(media_fullname, thumb_fullname, thumbsize)
        item = PostVideo(None, media_fullname, '/'.join(('.thumbnails', thumb_basename)),
                        thumbsize, infofmt)
    return item


# -- Creation of diary from medias --------------------------------------------


def create_index(args):
    # list of all pictures and movies
    medias = list_of_medias(args.imgsource, args.recursive)

    # list of required dates (the DCIM directory can contain images not related
    # with the desired index, e.g. two indexes for the same image directory)
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
        posts.append(Post.from_date(date))

    os.makedirs(args.root, exist_ok=True)
    print_markdown(posts, title, os.path.join(args.root, 'index.md'))


# -- Conversion to html page --------------------------------------------------


def make_basic_index(args):
    md_filename = os.path.join(args.root, 'index.md')
    if os.path.exists(md_filename):
        title, posts = parse_markdown(md_filename)
    elif args.extend:
        title = os.path.basename(args.root)
        posts = list()
    else:
        error('File not found', md_filename)

    for post in posts:
        for media in post.medias:
            media_fullname = os.path.join(args.root, media.uri)
            item = create_item(media_fullname, args.thumbdir, 'post', 400)
            media.thumb = item.thumb
            media.thumbsize = item.thumbsize
            media.descr = item.descr

    thumblist = []
    for post in posts:
        thumblist.extend([os.path.basename(media.thumb) for media in post.medias])
    purge_thumbnails(args.thumbdir, thumblist, 'post')

    return title, posts


def purge_thumbnails(thumbdir, thumblist, key):
    # purge thumbnail dir from irrelevant thumbnails (e.g. after renaming images)
    for fullname in glob.glob(os.path.join(thumbdir, f'{key}*.jpg')):
        if os.path.basename(fullname) not in thumblist:
            print('Removing thumbnail', fullname)
            os.remove(fullname)


def markdown_to_html(args):
    title, posts = make_basic_index(args)
    print_html(posts, title, os.path.join(args.dest, 'index.htm'), 'regular')


# -- Addition of DCIM medias --------------------------------------------------


def extend_index(args):
    title, posts = make_basic_index(args)

    # list of all pictures and movies
    medias = list_of_medias(args.imgsource, args.recursive)

    # list of required dates (the DCIM directory can contain medias not related
    # with the current page (e.g. two pages for the same image directory)
    required_dates = set()
    if args.dates:
        date1, date2 = args.dates.split('-')
        for media in medias:
            date = date_from_item(media)
            if date1 <= date <= date2:
                required_dates.add(date)
    else:
        for post in posts:
            if post.date:
                required_dates.add(post.date)

    bydate = defaultdict(list)
    thumbnails = list()
    for media_fullname in medias:
        date = date_from_item(media_fullname)  #  calculé deux fois
        if date in required_dates:
            item = create_item(media_fullname, args.thumbdir, 'dcim', 300)
            if item:
                thumb_fullname = os.path.join(args.dest, item.thumb)
                bydate[date].append(item)
                thumbnails.append(thumb_fullname)

    for date, liste in bydate.items():
        liste.sort(key=lambda item: time_from_item(item.uri))

    # make list of extra dates (not in posts)
    extradates = required_dates - {post.date for post in posts}

    # complete posts with extra dates from args.dates
    for date in extradates:
        bisect.insort(posts, Post.from_date(date))

    # several posts can have the same date, only the first one is completed with dcim medias
    for post in posts:
        if post.daterank == 1:
            post.dcim = bydate[post.date]

    thumblist = []
    for post in posts:
        thumblist.extend([os.path.basename(media.thumb) for media in post.dcim])
    purge_thumbnails(args.thumbdir, thumblist, 'dcim')

    print_html(posts, title, os.path.join(args.dest, 'index-x.htm'), 'regular')


def list_of_files(sourcedir, recursive):
    """ return the list of full paths for files in source directory
    """
    result = list()
    if recursive is False:
        for basename in os.listdir(sourcedir):
            result.append(os.path.join(sourcedir, basename))
    else:
        for root, dirs, files in os.walk(sourcedir):
            if '.thumbnails' not in root:
                for basename in files:
                    result.append(os.path.join(root, basename))
    return result


def list_of_medias(imgsource, recursive):
    """ return the list of full paths for pictures and movies in source directory
    """
    files = list_of_files(imgsource, recursive)
    return [_ for _ in files if is_media(_)]



# -- Export to blogger---------------------------------------------------------


def online_images_url(args):
    try:
        if args.urlblogger.startswith('http:') or args.urlblogger.startswith('https:'):
            with urlopen(args.urlblogger) as u:
                buffer = u.read()
        else:
            with open(args.urlblogger, 'rb') as f:
                buffer = f.read()
    except:
        error('Unable to read url', args.urlblogger)
    buffer = buffer.decode('utf-8')

    online_images = dict()
    for match in re.finditer('<div class="separator"((?!<div).)*?</div>', buffer, flags=re.DOTALL):
        div_separator = match.group(0)
        div_separator = div_separator.replace('&nbsp;', '')
        elem_div = objectify.fromstring(div_separator)
        for elem_a in elem_div.iterchildren(tag='a'):
            href = elem_a.get("href")
            thumb = elem_a.img.get("src")
            online_images[os.path.basename(href)] = (href, thumb)

    # video insertion relies only on video order
    online_videos = list()
    for match in re.finditer('<iframe allowfullscreen="allowfullscreen".*?</iframe>', buffer, flags=re.DOTALL):
        iframe = match.group(0)
        online_videos.append(iframe)

    return online_images, online_videos


def compare_image_buffers(imgbuf1, imgbuf2):
    with io.BytesIO(imgbuf1) as imgio1, io.BytesIO(imgbuf2) as imgio2:
        img1 = Image.open(imgio1)
        img2 = Image.open(imgio2)
        diff = ImageChops.difference(img1, img2)
        return not diff.getbbox()


def check_images(args, posts, online_images):
    result = True
    for post in posts:
        for media in post.medias:
            if type(media) is PostImage:
                if media.basename in online_images:
                    with open(os.path.join(args.root, media.uri), 'rb') as f:
                        imgbuf1 = f.read()
                    try:
                        with urlopen(online_images[media.basename][0]) as u:
                            imgbuf2 = u.read()
                    except FileNotFoundError:
                        print('File not found', online_images[media.basename][0])
                        next
                    if compare_image_buffers(imgbuf1, imgbuf2) is False:
                        print('Files are different, upload', media.basename)
                    else:
                        if 1:
                            print('File already online', media.basename)
                else:
                    print('File is absent, upload', media.basename)
                    result = False
            elif type(media) is PostVideo:
                # no check for the moment
                print('Video not checked', media.basename)
            else:
                assert False
    return result


def compose_blogger_html(title, posts, imgdata, online_videos):
    """ Compose html with blogger image urls
    """
    for post in posts:
        for media in post.medias:
            if type(media) is PostImage:
                if media.uri not in imgdata:
                    print('Image missing: ', media.uri)
                else:
                    img_url, resized_url = imgdata[media.uri]
                    media.uri = img_url
                    media.resized_url = resized_url
            elif type(media) is PostVideo:
                if not online_videos:
                    print('Video missing: ', media.uri)
                else:
                    media.iframe = online_videos[0]
                    del online_videos[0]
            else:
                assert False

    return print_html(posts, title, '', target='blogger')


def prepare_for_blogger(args):
    """
    Export blogger html to clipboard.
    If --full, export complete html, otherwise export html extract ready to
    paste into blogger edit mode.
    """
    title, posts = parse_markdown(os.path.join(args.root, 'index.md'))
    online_images, online_videos = online_images_url(args)

    if args.check_images and check_images(args, posts, online_images) is False:
        pass

    html = compose_blogger_html(title, posts, online_images, online_videos)

    if args.full is False:
        html = re.search('<body>(.*)?</body>', html, flags=re.DOTALL).group(1)
        html = re.sub('<script>.*?</script>', '', html, flags=re.DOTALL)
        html = STYLE.replace('%%', '%') + html

    clipboard.copy(html)


# -- Other commands -----------------------------------------------------------


def idempotence(args):
    title, posts = parse_markdown(os.path.join(args.root, 'index.md'))
    print_markdown(posts, title, os.path.join(args.dest, 'index.md'))


# -- Main ---------------------------------------------------------------------


def parse_command_line(argstring):
    parser = argparse.ArgumentParser(description=None, usage=USAGE)

    agroup = parser.add_argument_group('Commands')
    xgroup = agroup.add_mutually_exclusive_group()
    xgroup.add_argument('--create', help='create journal from medias in --imgsource',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--html', help='input md, output html',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--extend', help='extend image set, source in --imgsource',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--blogger',
                        help='input md, html blogger ready in clipboard',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--idem', help='test idempotence',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--test', help=argparse.SUPPRESS,
                        action='store')

    agroup = parser.add_argument_group('Parameters')
    agroup.add_argument('--dest', help='output directory',
                        action='store')
    agroup.add_argument('--year', help='year',
                        action='store', default=None)
    agroup.add_argument('--dates', help='dates interval for extended index',
                        action='store', default=None)
    agroup.add_argument('--imgsource', help='image source for extended index',
                        action='store', default=None)
    agroup.add_argument('--recursive', help='--imgsource scans recursively',
                        action='store_true', default=True)
    agroup.add_argument('--flat', dest='recursive', help='--imgsource does not recurse',
                        action='store_false')

    agroup.add_argument('--full', help='full html (versus blogger ready html)',
                        action='store_true', default=False)
    agroup.add_argument('--check', dest='check_images', help='check availability of medias on blogger',
                        action='store_true')
    agroup.add_argument('--url', dest='urlblogger', help='blogger post url',
                        action='store')

    if argstring is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(argstring.split())

    args.root = args.create or args.html or args.extend or args.blogger or args.idem

   # check and normalize paths

    if args.root:
        args.root = os.path.abspath(args.root)
        if not os.path.isdir(args.root):
            error('Directory not found', args.root)

    if args.dest:
        args.dest = os.path.abspath(args.dest)

    if args.dest is None:
        args.dest = args.root

    if args.extend and args.imgsource is None:
        error('No image source (--imgsource)')

    if args.imgsource:
        args.imgsource = os.path.abspath(args.imgsource)
        if not os.path.isdir(args.imgsource):
            error('Directory not found', args.imgsource)

    if args.blogger and args.urlblogger is None:
        error('No blogger url (--url)')

    if args.html or args.extend:
        # check for ffmpeg and ffprobe in path
        for exe in ('ffmpeg', 'ffprobe'):
            try:
                check_output([exe, '-version'])
            except FileNotFoundError:
                error('File not found', exe)

        args.thumbdir = os.path.join(args.dest, '.thumbnails')
        if not os.path.exists(args.thumbdir):
            os.mkdir(args.thumbdir)

        photoboxdir = os.path.join(args.dest, 'photobox')
        if not os.path.exists(photoboxdir):
            photoboxsrc = os.path.join(os.path.dirname(__file__), 'photobox')
            shutil.copytree(photoboxsrc, photoboxdir)

    return args


def warning(msg):
    print(msg)


# Every error message error must be declared here to give a return code to the error
ERRORS = '''\
File not found
Directory not found
No date in record
Posts are not ordered
Unable to read url
No image source (--imgsource)
No blogger url (--url)
'''


def errorcode(msg):
    return ERRORS.splitlines().index(msg) + 1


def error(*msg):
    print('**', ' '.join(msg))
    sys.exit(errorcode(msg[0]))


def main(argstring=None):
    locale.setlocale(locale.LC_TIME, '')
    args = parse_command_line(argstring)

    if args.create:
        create_index(args)

    elif args.html:
        markdown_to_html(args)

    elif args.extend:
        extend_index(args)

    elif args.blogger:
        prepare_for_blogger(args)

    elif args.idem:
        idempotence(args)

    elif args.test:
        pass


if __name__ == '__main__':
    main()
