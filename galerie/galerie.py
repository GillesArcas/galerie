"""
Make html galleries from media directories. Organize by dates, by subdirs or by
the content of a diary file. The diary file is a markdown file organized by
dates, each day described by a text and some medias (photos and movies).

The diary file can be exported to:
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

from configparser import ConfigParser
from collections import defaultdict
from subprocess import check_output, CalledProcessError, STDOUT
from urllib.request import urlopen

import colorama
import clipboard
import PIL
from PIL import Image, ImageChops
from lxml import objectify
import markdown


USAGE = """
galerie --gallery <root-dir> [--sourcedir <media-dir>]
                             [--bydir true|false*]
                             [--bydate true|false*]
                             [--diary true|false*]
                             [--recursive true|false*]
                             [--dates source*|diary|<yyyymmdd-yyyymmdd>]
                             [--dest <directory>]
                             [--forcethumb]
galerie --gallery <root-dir> [--update]
galerie --create  <root-dir> --sourcedir <media-dir>
                             [--recursive true|false*]
                             [--dates source*|<yyyymmdd-yyyymmdd>]
galerie --blogger <root-dir> --url <url>
                             [--check]
                             [--full]

Notes:
    - * gives default
    - all options can be abbreviated is there is no conflict with other options (--gallery --> --gal)

"""


# -- Post objects -------------------------------------------------------------


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
    <link rel="icon" href="favicon.ico" />
    <meta name="viewport" content="width=device-width">
    <link rel="stylesheet" href="photobox/photobox.css">
    <script src="photobox/jquery.min.js"></script>
    <script src="photobox/jquery.photobox.js"></script>
{CAPTION_IMAGE_STYLE}
{STYLE}
</head>

<body>\
'''

BUTTONS = '''\
<button id="btn_full" type="button" style="position: fixed; width: 50px; top: 20px; right: 20px; background-color:white">Full</button>
<button id="btn_blog" type="button" style="position: fixed; width: 50px; top: 40px; right: 20px; background-color:white">Diary</button>
<button id="btn_text" type="button" style="position: fixed; width: 50px; top: 60px; right: 20px; background-color:white">Text</button>

<script>
$('#btn_full').click(function() {
    $("[id^=gallery-blog]").show();
    $("[id^=gallery-dcim]").show();
    $("div.extra").show();
});
$('#btn_text').click(function() {
    $("[id^=gallery-blog]").hide();
    $("[id^=gallery-dcim]").hide();
    $("div.extra").hide();
});
$('#btn_blog').click(function() {
    $("[id^=gallery-blog]").show();
    $("[id^=gallery-dcim]").hide();
    $("div.extra").hide();
});
</script>
'''

SUBDIR_BACKCOL = '#eee'
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

DIRPOST = '<a href="%s"><img src="%s" width="%d" height="%d" style="border: 1px solid #C0C0C0;" /></a>'
DIRPOSTCAPTION = f'''
<span style="background-color:{SUBDIR_BACKCOL}; margin-bottom: 8px; border: 1px solid #C0C0C0;">
<a href="%s"><img src="%s" width="%d" height="%d" style="border: 1px solid #C0C0C0;" /></a>
<p style="margin-left:2px;">%s</p>
</span>
'''
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
        self.extra = False

    def __lt__(self, other):
        return self.date < other.date

    @classmethod
    def from_markdown(cls, post):
        m = re.match(r'\[([0-9/]{10})\]\n*', post[0])
        if m:
            date = m.group(1).replace('/', '')
            del post[0]
        else:
            error('No date in post', ' '.join(post))

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

    def to_html(self, args, target='regular'):
        if target == 'regular':
            if args.diary:
                return self.to_html_diary(args)
            else:
                return self.to_html_regular(args)
        if target == 'blogger':
            return self.to_html_blogger()

    def to_html_regular(self, args):
        html = list()
        if self.text:
            # possible with --bydate
            html.append(markdown.markdown(self.text))
        subdirs, dcim = dispatch_post_items(self.dcim)
        if self.dcim:
            html.append(SEP)
        for media in subdirs:
            html.append(media.to_html_dcim(args))
        if dcim:
            html.append(f'<div id="gallery-dcim-{self.date}-{self.daterank}">')
            for media in dcim:
                html.append(media.to_html_dcim(args))
            html.append('</div>')

        html.append(SEP)
        return html

    def to_html_diary(self, args):
        html = list()
        if self.extra:
            html.append('<div class="extra">')

        if self.text:
            html.append(markdown.markdown(self.text))

        if self.medias:
            html.append(f'<div id="gallery-blog-{self.date}-{self.daterank}">')
            for media in self.medias:
                html.append(media.to_html_post(args))
            html.append('</div>')

        _, dcim = dispatch_post_items(self.dcim)
        if dcim:
            html.append(f'<div id="gallery-dcim-{self.date}-{self.daterank}">')
            html.append(SEP)
            for media in dcim:
                html.append(media.to_html_dcim(args))
            html.append('</div>')

        html.append(SEP)
        if self.extra:
            html.append('</div>')
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

    def to_html_post(self, args):
        descr = self.descr if args.thumbnails.media_description else ''
        if not self.caption:
            return IMGPOST % (self.uri, self.thumb, *self.thumbsize, descr)
        else:
            return IMGPOSTCAPTION % (self.uri, self.thumb, *self.thumbsize, descr, self.caption)

    def to_html_dcim(self, args):
        descr = self.descr if args.thumbnails.media_description else ''
        return IMGDCIM % (self.uri, self.thumb, *self.thumbsize, descr)

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

    def to_html_post(self, args):
        descr = self.descr if args.thumbnails.media_description else ''
        if not self.caption:
            return VIDPOST % (self.uri, self.thumb, *self.thumbsize, descr)
        else:
            return VIDPOSTCAPTION % (self.uri, self.thumb, *self.thumbsize, descr, self.caption)

    def to_html_dcim(self, args):
        descr = self.descr if args.thumbnails.media_description else ''
        return VIDDCIM % (self.uri, self.thumb, *self.thumbsize, descr)

    def to_html_blogger(self):
        x = f'<p style="text-align: center;">{self.iframe}</p>'
        if not self.caption:
            return x
        else:
            return f'%s\n{CAPTION_PAT}' % (x, self.caption)


class PostSubdir(PostItem):
    def to_html_dcim(self, args):
        basename = os.path.basename(self.htmname)
        posts = self.posts
        title = self.caption
        print_html(args, posts, title, self.htmname)

        if not self.caption:
            return DIRPOST % (basename, self.thumb, *self.thumbsize)
        else:
            return DIRPOSTCAPTION % (basename, self.thumb, *self.thumbsize, self.caption)


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


def compose_html_reduced(args, posts, title, target):
    html = list()
    html.append(START % title)

    for post in posts:
        for line in post.to_html(args, target):
            html.append(line.strip())
        html.append('')

    html.append(END)
    return html


def compose_html_full(args, posts, title, target):
    html = list()
    html.append(START % title)

    if args.diary:
        html.append(BUTTONS)

    for post in posts:
        for line in post.to_html(args, target):
            html.append(line.strip())
        html.append('')

    html.append('<script>')
    for post in posts:
        if post.medias:
            gallery_id = f'gallery-blog-{post.date}-{post.daterank}'
            html.append(gallery_call(args, gallery_id))
        if post.dcim:
            gallery_id = f'gallery-dcim-{post.date}-{post.daterank}'
            html.append(gallery_call(args, gallery_id))
    html.append('</script>')

    html.append(END)
    return html


def print_html_to_stream(args, posts, title, stream, target):
    if target == 'regular':
        for line in compose_html_full(args, posts, title, target):
            print(line, file=stream)
    else:
        for line in compose_html_reduced(args, posts, title, target):
            print(line, file=stream)


def print_html(args, posts, title, html_name, target='regular'):
    assert target in ('regular', 'blogger')
    if html_name:
        with open(html_name, 'wt', encoding='utf-8') as f:
            print_html_to_stream(args, posts, title, f, target)
            return None
    else:
        with io.StringIO() as f:
            print_html_to_stream(args, posts, title, f, target)
            return f.getvalue()


GALLERYCALL = """
$('#%s').photobox('a', {
loop:%s,
thumbs:%s,
autoplay:%s,
time:%d,
zoomable:%s ,
rotatable:%s,
wheelNextPrev:%s
});
"""


def gallery_call(args, gallery_id):
    return GALLERYCALL.replace('\n', '') % (
        gallery_id,
        str(args.photobox.loop).lower(),
        str(args.photobox.thumbs).lower(),
        str(args.photobox.autoplay).lower(),
        args.photobox.time,
        str(args.photobox.zoomable).lower(),
        str(args.photobox.rotatable).lower(),
        str(args.photobox.wheelNextPrev).lower(),
    )


# -- Media description --------------------------------------------------------


def is_image_file(name):
    return os.path.splitext(name)[1].lower() in (
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif'
    )


def is_video_file(name):
    return os.path.splitext(name)[1].lower() in (
        '.mp4', '.webm', '.mkv', '.flv', '.m4v', '.avi', '.wmv', '.mts', '.vob', '.divx'
    )


def is_media(name):
    return is_image_file(name) or is_video_file(name)


def date_from_name(name):
    # heuristics
    if match := re.search(r'(?:[^0-9]|^)(\d{8})([^0-9]|$)', name):
        digits = match.group(1)
        year, month, day = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
        if 2000 <= year <= datetime.date.today().year and 1 <= month <= 12 and 1 <= day <= 31:
            return digits
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
    return None


def time_from_item(filename):
    if time := time_from_name(filename):
        return time
    else:
        timestamp = os.path.getmtime(filename)
        return datetime.datetime.fromtimestamp(timestamp).strftime('%H%M%S')


FFPROBE_CMD = '''\
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


def get_video_info(filename, info_fullname):
    if os.path.exists(info_fullname):
        with open(info_fullname) as f:
            info = f.readline().split()
        date, time, width, height, size, duration, fps = info[0], info[1], int(info[2]), int(info[3]), float(info[4]), int(info[5]), float(info[6])
        formatted_info = format_video_info(date, time, width, height, size, duration, fps)
        return (date, time, width, height, size, duration, fps), formatted_info
    else:
        info, formatted_info = make_video_info(filename, info_fullname)
        with open(info_fullname, 'wt') as f:
            print(' '.join([str(_) for _ in info]), file=f)
        return info, formatted_info


def make_video_info(filename, info_fullname):
    # ffmpeg must be in path
    date = date_from_item(filename)
    time = time_from_item(filename)
    command = [*FFPROBE_CMD.split(), filename]
    try:
        output = check_output(command, stderr=STDOUT).decode()
        width, height, fps, duration = parse_ffprobe_output(output)
        size = round(os.path.getsize(filename) / 1e6, 1)
        output = format_video_info(date, time, width, height, size, duration, fps)
    except CalledProcessError as e:
        output = e.output.decode()
        warning(output)
        raise
    return (date, time, width, height, size, duration, fps), output


def parse_ffprobe_output(ffprobe_output):
    # parse first channel data and last line for duration
    match = re.match(r'(\d+),(\d+),(\d+)/(\d+),(\d+/\d+).*\s(\d+\.\d+)', ffprobe_output, re.DOTALL)
    width = int(match.group(1))
    height = int(match.group(2))
    fps = round(int(match.group(3)) / int(match.group(4)), 1)
    duration = round(float(match.group(6)))
    return width, height, fps, duration


def format_video_info(date, time, width, height, size, duration, fps):
    return f'{date} {time}, dim={width}x{height}, {format_duration(duration)}, fps={fps}, {size} MB'


def format_duration(duration):
    mn = duration // 60
    sec = duration % 60
    if mn <= 59:
        return f'm:s={mn:02}:{sec:02}'
    else:
        hour = mn // 60
        mn = mn % 60
        return f'h:m:s={hour:02}:{mn:02}:{sec:02}'


# -- Thumbnails (image and video) ---------------------------------------------


def thumbname(name, key):
    return key + '-' + name + '.jpg'


def size_thumbnail(width, height, maxdim):
    if width >= height:
        return maxdim, int(round(maxdim * height / width))
    else:
        return int(round(maxdim * width / height)), maxdim


def make_thumbnail_image(args, image_name, thumb_name, size):
    if os.path.exists(thumb_name) and args.forcethumb is False:
        pass
    else:
        print('Making thumbnail:', thumb_name)
        create_thumbnail_image(image_name, thumb_name, size)


def create_thumbnail_image(image_name, thumb_name, size):
    imgobj = Image.open(image_name)

    if (imgobj.mode != 'RGBA'
        and image_name.endswith('.jpg')
        and not (image_name.endswith('.gif') and imgobj.info.get('transparency'))
       ):
        imgobj = imgobj.convert('RGBA')

    imgobj.thumbnail(size, Image.LANCZOS)
    imgobj = imgobj.convert('RGB')
    imgobj.save(thumb_name)


def make_thumbnail_video(args, video_name, thumb_name, size, duration):
    if os.path.exists(thumb_name) and args.forcethumb is False:
        pass
    else:
        print('Making thumbnail:', thumb_name)
        create_thumbnail_video(args, video_name, thumb_name, size, duration)


# base64 video.png
VIDEO_ICON = '''\
iVBORw0KGgoAAAANSUhEUgAAABgAAAAUCAAAAACy3qJfAAAA4UlEQVR4
2m1QoRbCMAy88SaK69xscfuEWiS4SZBIcCCRfAL8An8AcnJzTOJSWdxwzJXSPUoHRPQlueYuucigxm
9kDGaMf8AjopGcYn8LmmyLoihBWBiThb+5MTuUsc3aL56upneZ9sByAIg8Z8BEn96EeZ65iU7DvmbP
PxqDcH6p1swXBC4l6yZskACkTN1WrQr2SlIFhTtgqeZa+zsOogLXegvEocZ5c/W5BcoVNNCg3hSudV
/hEh4ofw6cEb00Km8i0dpRDUXfKiaQOEAdrUDo4dFp9C33jjaRac9/gDF/AlplVYtfWGCjAAAAAElF
TkSuQmCC'''


def create_thumbnail_video(args, filename, thumbname, size, duration):
    # ffmpeg must be in path
    delay = min(duration - 1, args.thumbnails.thumbdelay)
    sizearg = '%dx%d' % size
    command = 'ffmpeg -y -v error -itsoffset -%d -i "%s" -vcodec mjpeg -vframes 1 -an -f rawvideo -s %s "%s"'
    command = command % (delay, filename, sizearg, thumbname)
    result = os.system(command)

    # add a movie icon to the thumbnail to identify videos
    try:
        img1 = Image.open(thumbname)
    except:
        # ffmpeg was unable to save thumbnail
        warning('Unable to save thumbnail for', filename)
        return
    img2 = Image.open(io.BytesIO(base64.b64decode(VIDEO_ICON)))
    width, height = img1.size
    img1.paste(img2, (6, height - 20 - 6), None)
    img1.save(thumbname)


def make_thumbnail_subdir(args, subdir_name, thumb_name, size, items, thumbdir):
    # subdir thumbnails are always created as they depend on the content of the
    # directory
    print('Making thumbnail:', thumb_name)
    create_thumbnail_subdir(subdir_name, thumb_name, size, items, thumbdir)


def create_thumbnail_subdir(subdir_name, thumb_name, size, items, thumbdir):

    def size_thumbnail(width, height, xmax, ymax):
        width2 = xmax
        height2 = int(round(xmax * height / width))
        if height2 < ymax:
            width2 = int(round(ymax * width / height))
            height2 = ymax
        return width2, height2

    thumblist = [os.path.basename(item.thumb) for item in items]
    widthnum, heightnum, width, height, offsetx, offsety = mosaic_geometry(size, thumblist)
    thumbnum = widthnum * heightnum
    img = Image.new('RGB', size, SUBDIR_BACKCOL)

    for ind, thumb in enumerate(thumblist[:min(thumbnum, len(thumblist))]):
        row = ind // widthnum
        col = ind % widthnum
        img2 = Image.open(os.path.join(thumbdir, thumb))
        w, h = size_thumbnail(*img2.size, width[col], height[row])
        cropdim = ((w - width[col]) // 2, (h - height[row]) // 2,
                   (w - width[col]) // 2 + width[col], (h - height[row]) // 2 + height[row])
        img2 = img2.resize((w, h), Image.LANCZOS)
        img2 = img2.crop(cropdim)
        img.paste(img2, (offsetx[col], offsety[row]))
    img.save(thumb_name)


def mosaic_geometry(size, thumblist):
    if len(thumblist) == 1:
        widthnum = 1
        heightnum = 1
    elif len(thumblist) <= 3:
        widthnum = 1
        heightnum = 2
    elif len(thumblist) <= 8:
        widthnum = 2
        heightnum = 2
    else:
        widthnum = 3
        heightnum = 3

    if widthnum == 1:
        width = [size[0] - 2]
    else:
        width = [size[0] // widthnum - 2] * (widthnum - 1)
        width.append(size[0] - (1 + sum(width) + 2 * len(width) + 1))

    if heightnum == 1:
        height = [size[1] - 2]
    else:
        height = [size[1] // heightnum - 2] * (heightnum - 1)
        height.append(size[1] - (1 + sum(height) + 2 * len(height) + 1))

    offsetx = [1]
    for w in width[:-1]:
        offsetx.append(offsetx[-1] + w + 2)

    offsety = [1]
    for h in height[:-1]:
        offsety.append(offsety[-1] + h + 2)

    return widthnum, heightnum, width, height, offsetx, offsety


def list_of_thumbnails(posts, diary=False):
    thumblist = list()
    for post in posts:
        thumblist.extend(list_of_thumbnails_in_items(post.medias))
        if diary is False:
            thumblist.extend(list_of_thumbnails_in_items(post.dcim))
    return thumblist


def list_of_thumbnails_in_items(itemlist):
    thumblist = list()
    for item in itemlist:
        if type(item) == PostSubdir:
            thumblist.append(os.path.basename(item.thumb))
            thumblist.extend(list_of_thumbnails_in_items(item.sublist))
        else:
            thumblist.append(os.path.basename(item.thumb))
    return thumblist


def purge_thumbnails(thumbdir, posts, diary=False):
    """
    Purge thumbnail dir from irrelevant thumbnails (e.g. after renaming images)
    """
    thumblist = list_of_thumbnails(posts, diary)
    for fullname in glob.glob(os.path.join(thumbdir, '*.jpg')):
        if os.path.basename(fullname) not in thumblist:
            print('Removing thumbnail', fullname)
            os.remove(fullname)
            info_fullname = os.path.splitext(fullname)[0] + '.info'
            if os.path.exists(info_fullname):
                os.remove(info_fullname)


# -- List of medias helpers ---------------------------------------------------


def list_of_files(sourcedir, recursive):
    """
    Return the list of full paths for files in source directory
    """
    result = list()
    if recursive is False:
        listdir = sorted(os.listdir(sourcedir), key=str.lower)
        if '.nomedia' not in listdir:
            for basename in os.listdir(sourcedir):
                result.append(os.path.join(sourcedir, basename))
    else:
        for root, dirs, files in os.walk(sourcedir):
            if '.nomedia' not in files:
                for basename in files:
                    result.append(os.path.join(root, basename))
    return result


def list_of_medias(sourcedir, recursive):
    """
    Return the list of full paths for pictures and movies in source directory
    """
    files = list_of_files(sourcedir, recursive)
    return [_ for _ in files if is_media(_)]


def list_of_medias_ext(sourcedir):
    """
    Return the list of full paths for pictures and movies in source directory
    plus subdirectories containing media
    """
    result = list()
    listdir = sorted(os.listdir(sourcedir), key=str.lower)
    if '.nomedia' not in listdir:
        for basename in listdir:
            fullname = os.path.join(sourcedir, basename)
            if os.path.isdir(fullname) and basename != '$RECYCLE.BIN' and contains_media(fullname):
                result.append(fullname)
            else:
                if is_media(basename):
                    result.append(fullname)
    return result


def contains_media(fullname):
    for root, dirs, files in os.walk(fullname):
        if '.nomedia' not in files:
            for basename in files:
                if is_media(basename):
                    return True
    else:
        return False


def dispatch_post_items(list_of_post_items):
    subdirs = [_ for _ in list_of_post_items if type(_) is PostSubdir]
    medias = [_ for _ in list_of_post_items if type(_) is not PostSubdir]
    return subdirs, medias


# -- Creation of gallery element ----------------------------------------------


def create_item(args, media_fullname, sourcedir, thumbdir, key, thumbmax):
    if os.path.isfile(media_fullname):
        if is_image_file(media_fullname):
            return create_item_image(args, media_fullname, sourcedir, thumbdir, key, thumbmax)
        else:
            return create_item_video(args, media_fullname, sourcedir, thumbdir, key, thumbmax)
    else:
        return create_item_subdir(args, media_fullname, sourcedir, thumbdir, key, thumbmax)


def create_item_image(args, media_fullname, sourcedir, thumbdir, key, thumbmax):
    media_basename = os.path.basename(media_fullname)
    media_relname = relative_name(media_fullname, sourcedir)
    thumb_basename = thumbname(media_relname, key)
    thumb_fullname = os.path.join(thumbdir, thumb_basename)

    try:
        info, infofmt = get_image_info(media_fullname)
        infofmt = media_basename + ': ' + infofmt
        thumbsize = size_thumbnail(info[2], info[3], thumbmax)
        make_thumbnail_image(args, media_fullname, thumb_fullname, thumbsize)
        return PostImage(None, media_fullname, '/'.join(('.thumbnails', thumb_basename)),
                         thumbsize, infofmt)
    except PIL.UnidentifiedImageError:
        # corrupted image
        warning('Unable to read image', media_fullname)
        return None


def create_item_video(args, media_fullname, sourcedir, thumbdir, key, thumbmax):
    media_basename = os.path.basename(media_fullname)
    media_relname = relative_name(media_fullname, sourcedir)
    thumb_basename = thumbname(media_relname, key)
    thumb_fullname = os.path.join(thumbdir, thumb_basename)
    info_fullname = os.path.splitext(thumb_fullname)[0] + '.info'

    try:
        info, infofmt = get_video_info(media_fullname, info_fullname)
        infofmt = media_basename + ': ' + infofmt
        thumbsize = size_thumbnail(info[2], info[3], thumbmax)
        make_thumbnail_video(args, media_fullname, thumb_fullname, thumbsize, duration=info[5])
        return PostVideo(None, media_fullname, '/'.join(('.thumbnails', thumb_basename)),
                         thumbsize, infofmt)
    except CalledProcessError:
        # corrupted video
        warning('Unable to read video', media_fullname)
        return None


def create_item_subdir(args, media_fullname, sourcedir, thumbdir, key, thumbmax):
    media_basename = os.path.basename(media_fullname)
    media_relname = relative_name(media_fullname, sourcedir)
    thumb_basename = thumbname(media_relname, key)
    thumb_fullname = os.path.join(thumbdir, thumb_basename)

    info, infofmt = None, None
    thumbsize = (thumbmax, int(round(thumbmax / 640 * 480)))

    medias_ext = list_of_medias_ext(media_fullname)
    if not medias_ext:
        return None

    item = PostSubdir(None, media_fullname, '/'.join(('.thumbnails', thumb_basename)),
                    thumbsize, infofmt)
    item.htmname = os.path.join(os.path.dirname(thumbdir), media_relname + '.htm')
    if args.thumbnails.subdir_caption:
        item.caption = media_basename
    else:
        item.caption = ''

    _, posts = make_posts(args, media_fullname)
    item.posts = posts
    items = [item for post in posts for item in post.dcim]
    item.sublist = items

    make_thumbnail_subdir(args, media_fullname, thumb_fullname, thumbsize, items, thumbdir)
    return item


def relative_name(media_fullname, sourcedir):
    """
    /Gilles/Dev/journal/tests/subdir/deeper2/deepest/OCT_20000112_000004.jpg
    -->
    deeper2_deepest_OCT_20000112_000004.jpg

    /Gilles/Dev/journal/tests/subdir/deeper2/deepest
    -->
    deeper2_deepest
    """
    x = os.path.relpath(media_fullname, sourcedir)
    x = x.replace('\\', '_').replace('/', '_').replace('#', '_')
    return x


# -- Creation of posts --------------------------------------------------------


def make_posts(args, dirname):
    if args.diary is True:
        if not args.sourcedir:
            return make_posts_from_diary(args)
        else:
            return make_posts_from_diary_and_dir(args)
    elif args.bydate is False:
        return make_posts_from_subdir(args, dirname)
    else:
        return make_posts_from_subdir_and_date(args, dirname)


def make_posts_from_diary(args):
    md_filename = os.path.join(args.root, 'index.md')
    if os.path.exists(md_filename):
        title, posts = parse_markdown(md_filename)
    else:
        error('File not found', md_filename)

    for post in posts:
        for media in post.medias:
            media_fullname = os.path.join(args.root, media.uri)
            ##item = create_item(args, media_fullname, args.sourcedir, args.thumbdir, 'post', 400)
            item = create_item(args, media_fullname, args.root, args.thumbdir, 'post', 400)
            media.thumb = item.thumb
            media.thumbsize = item.thumbsize
            media.descr = item.descr

    return title, posts


def create_items_by_date(args, medias, posts):
    # list of required dates
    if args.dates == 'diary':
        required_dates = {post.date for post in posts}
    else:
        required_dates = {date_from_item(media) for media in medias}
        if type(args.dates) == tuple:
            date1, date2 = args.dates
            required_dates = {date for date in required_dates if date1 <= date <= date2}

    bydate = defaultdict(list)
    for media_fullname in medias:
        date = date_from_item(media_fullname)
        if date in required_dates:
            item = create_item(args, media_fullname, args.sourcedir, args.thumbdir, 'dcim', 300)
            if item:
                bydate[date].append(item)

    for date, liste in bydate.items():
        liste.sort(key=lambda item: time_from_item(item.uri))

    return bydate


def make_posts_from_diary_and_dir(args):
    title, posts = make_posts_from_diary(args)

    # list of all pictures and movies
    medias = list_of_medias(args.sourcedir, args.recursive)

    bydate = create_items_by_date(args, medias, posts)

    # make list of extra dates (not in posts)
    extradates = set(bydate) - {post.date for post in posts}

    # complete posts with extra dates
    for date in extradates:
        post = Post.from_date(date)
        post.extra = True
        bisect.insort(posts, post)

    # several posts can have the same date, only the first one is completed with dcim medias
    for post in posts:
        if post.date in bydate and post.daterank == 1:
            post.dcim = bydate[post.date]

    return title, posts


def make_posts_from_subdir(args, dirname):
    # list of pictures and movies plus subdirectories
    if args.bydir is False:
        medias_ext = list_of_medias(dirname, args.recursive)
    else:
        medias_ext = list_of_medias_ext(dirname)

    # complete posts
    postmedias = list()
    for item in medias_ext:
        postmedia = create_item(args, item, args.sourcedir, args.thumbdir, 'dcim', 300)
        if postmedia is not None:
            postmedias.append(postmedia)

    post = Post(date='00000000', text='', medias=[])
    post.dcim = postmedias
    posts = [post]
    title = os.path.basename(args.sourcedir) or os.path.splitdrive(args.sourcedir)[0]

    return title, posts


def make_posts_from_subdir_and_date(args, dirname):
    # list of all pictures and movies
    if args.bydir is False:
        medias = list_of_medias(dirname, args.recursive)
        subdirs = []
    else:
        medias_ext = list_of_medias_ext(dirname)
        medias = [_ for _ in medias_ext if is_media(_)]
        subdirs = [_ for _ in medias_ext if not is_media(_)]

    # create list of posts with a single post containing all subdirs
    posts = list()
    items = list()
    for media_fullname in subdirs:
        item = create_item(args, media_fullname, args.sourcedir, args.thumbdir, 'dcim', 300)
        if item:
            items.append(item)
    if items:
        post = Post(date='00000000', text='', medias=[])
        post.dcim = items
        posts.append(post)

    bydate = create_items_by_date(args, medias, posts)

    # add dates
    for date in sorted(bydate):
        post = Post.from_date(date)
        post.dcim = bydate[post.date]
        posts.append(post)
    title = os.path.basename(args.sourcedir) or os.path.splitdrive(args.sourcedir)[0]

    return title, posts


# -- Creation of html page from directory tree --------------------------------


def create_gallery(args):
    title, posts = make_posts(args, args.sourcedir)
    print_html(args, posts, title, os.path.join(args.dest, args.rootname), 'regular')
    if args.diary and not args.sourcedir:
        purge_thumbnails(args.thumbdir, posts, diary=True)
    else:
        purge_thumbnails(args.thumbdir, posts)


# -- Creation of diary from medias --------------------------------------------


def create_diary(args):
    # list of all pictures and movies
    medias = list_of_medias(args.sourcedir, args.recursive)

    # list of required dates
    if args.dates == 'diary':
        assert 0
    else:
        required_dates = {date_from_item(media) for media in medias}
        if type(args.dates) == tuple:
            date1, date2 = args.dates
            required_dates = {date for date in required_dates if date1 <= date <= date2}

    title = args.sourcedir
    posts = list()
    for date in sorted(required_dates):
        posts.append(Post.from_date(date))

    os.makedirs(args.root, exist_ok=True)
    print_markdown(posts, title, os.path.join(args.root, 'index.md'))


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


def compose_blogger_html(args, title, posts, imgdata, online_videos):
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

    return print_html(args, posts, title, '', target='blogger')


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

    html = compose_blogger_html(args, title, posts, online_images, online_videos)

    if args.full is False:
        html = re.search('<body>(.*)?</body>', html, flags=re.DOTALL).group(1)
        html = re.sub('<script>.*?</script>', '', html, flags=re.DOTALL)
        html = STYLE.replace('%%', '%') + html

    clipboard.copy(html)


# -- Other commands -----------------------------------------------------------


def idempotence(args):
    title, posts = parse_markdown(os.path.join(args.root, 'index.md'))
    print_markdown(posts, title, os.path.join(args.dest, 'index.md'))


# -- Configuration file ------------------------------------------------------


# The following docstring is used to create the configuration file.
CONFIG_DEFAULTS = """\
[source]

; source directory
; value: valid path
sourcedir = .

; one web page per directory
; value: true or false
bydir = false

; dispatch medias by dates
; value: true or false
bydate = false

; include text and medias from diary file
; value: true or false
diary = false

; include subdirectories recursively (used when bydir is false)
; value: true or false
recursive = false

; interval of dates to include
; value: yyyymmdd-yyyymmdd or empty
dates =

[thumbnails]

; specifies whether or not the gallery displays media description (size, dimension, etc)
; value: true or false
media_description = true

; specifies whether subdir captions are empty or the name of the subdir
; value: true or false
subdir_caption = true

; timestamp of thumbnail in video
; value: number of seconds
thumbdelay = 5

[photobox]

; Allows to navigate between first and last images
; value: true or false
loop = false

; Show gallery thumbnails below the presented photo
; value: true or false
thumbs = true

; Should autoplay on first time or not
; value: true or false
autoplay = false

; Autoplay interval (less than 1000 will hide the autoplay button)
; value: milliseconds
time = 3000

; Disable/enable mousewheel image zooming
; value: true or false
zoomable = true

; Allow rotation of the image
; value: true or false
rotatable = true

; Change image using mousewheel left/right
; value: true or false
wheelNextPrev = true
"""


class MyConfigParser (ConfigParser):
    """Add input checking."""
    def __init__(self):
        ConfigParser.__init__(self, inline_comment_prefixes=(';',))

    def error(self, section, entry):
        error('missing or incorrect config value:', '[%s]%s' % (section, entry))

    def getint(self, section, entry):
        try:
            return ConfigParser.getint(self, section, entry)
        except Exception as e:
            print(e)
            self.error(section, entry)

    def getboolean(self, section, entry):
        try:
            return ConfigParser.getboolean(self, section, entry)
        except Exception as e:
            print(e)
            self.error(section, entry)


def configfilename(params):
    return os.path.join(params.root, '.config.ini')


def createconfig(config_filename):
    with open(config_filename, 'wt') as f:
        f.writelines(CONFIG_DEFAULTS)


def read_config(params):
    config_filename = configfilename(params)

    try:
        if not os.path.exists(config_filename) or params.resetcfg:
            createconfig(config_filename)
    except:
        error('error creating configuration file')

    try:
        getconfig(params, config_filename)
    except Exception as e:
        error('error reading configuration file.', str(e), 'Use --resetcfg')


def getconfig(options, config_filename):
    class Section:
        pass

    options.source = Section()
    options.thumbnails = Section()
    options.photobox = Section()

    config = MyConfigParser()
    config.read(config_filename)

    # [source]
    options.source.sourcedir = config.get('source', 'sourcedir')
    options.source.bydir = config.getboolean('source', 'bydir')
    options.source.bydate = config.getboolean('source', 'bydate')
    options.source.diary = config.getboolean('source', 'diary')
    options.source.recursive = config.getboolean('source', 'recursive')
    options.source.dates = config.get('source', 'dates')

    # [thumbnails]
    options.thumbnails.media_description = config.getboolean('thumbnails', 'media_description')
    options.thumbnails.subdir_caption = config.getboolean('thumbnails', 'subdir_caption')
    options.thumbnails.thumbdelay = config.getint('thumbnails', 'thumbdelay')

    # [photobox]
    options.photobox.loop = config.getboolean('photobox', 'loop')
    options.photobox.thumbs = config.getboolean('photobox', 'thumbs')
    options.photobox.autoplay = config.getboolean('photobox', 'autoplay')
    options.photobox.time = config.getint('photobox', 'time')
    options.photobox.zoomable = config.getboolean('photobox', 'zoomable')
    options.photobox.rotatable = config.getboolean('photobox', 'rotatable')
    options.photobox.wheelNextPrev = config.getboolean('photobox', 'wheelNextPrev')


def setconfig(cfgname, section, key, value):
    config = MyConfigParser()
    config.read(cfgname)
    config.set(section, key, value)
    with open(cfgname, 'wt') as configfile:
        config.write(configfile)


def setconfig_cmd(args):
    config_filename = configfilename(args)
    setconfig(config_filename, *args.setcfg)


def update_config(args):
    # update only entries which can be modified from the command line (source section)
    # manual update to keep comments
    cfgname = configfilename(args)
    with open(cfgname) as f:
        cfglines = [_.strip() for _ in f.readlines()]

    updates = (
        ('sourcedir', args.sourcedir),
        ('bydir', args.bydir),
        ('bydate', args.bydate),
        ('diary', args.diary),
        ('recursive', args.recursive),
        ('dates', args.dates),
    )

    for key, value in updates:
        print(key, value)
        for iline, line in enumerate(cfglines):
            if line.startswith(key):
                cfglines[iline] = f'{key} = {value}'
                break

    with open(cfgname, 'wt') as f:
        for line in cfglines:
            print(line, file=f)


# -- Error handling -----------------------------------------------------------


def warning(*msg):
    print(colorama.Fore.YELLOW + colorama.Style.BRIGHT +
          ' '.join(msg),
          colorama.Style.RESET_ALL)


# Every error message error must be declared here to give a return code to the error
ERRORS = '''\
File not found
Directory not found
No date in post
Posts are not ordered
Unable to read url
No image source (--sourcedir)
No blogger url (--url)
missing or incorrect config value:
error creating configuration file
error reading configuration file.
Incorrect date format
'''


def errorcode(msg):
    return ERRORS.splitlines().index(msg) + 1


def error(*msg):
    print(colorama.Fore.RED + colorama.Style.BRIGHT +
          ' '.join(msg),
          colorama.Style.RESET_ALL)
    sys.exit(errorcode(msg[0]))


# -- Main ---------------------------------------------------------------------


BOOL = ('true', 'false')


def parse_command_line(argstring):
    parser = argparse.ArgumentParser(description=None, usage=USAGE)

    agroup = parser.add_argument_group('Commands')
    xgroup = agroup.add_mutually_exclusive_group()
    xgroup.add_argument('--gallery', help='source in --sourcedir',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--create', help='create journal from medias in --sourcedir',
                        action='store', metavar='<root-dir>')
    # testing
    xgroup.add_argument('--resetcfg', help='reset config file to defaults',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--setcfg', help='set field in config file',
                        action='store', nargs=4, metavar='<root-dir>')
    xgroup.add_argument('--idem', help='test idempotence',
                        action='store', metavar='<root-dir>')
    xgroup.add_argument('--test', help=argparse.SUPPRESS,
                        action='store')
    # blogger
    xgroup.add_argument('--blogger',
                        help='input md, html blogger ready in clipboard',
                        action='store', metavar='<root-dir>')

    agroup = parser.add_argument_group('Parameters')
    agroup.add_argument('--bydir', help='organize gallery by subdirectory',
                        action='store', default='false', choices=BOOL)
    agroup.add_argument('--bydate', help='organize gallery by date',
                        action='store', default='false', choices=BOOL)
    agroup.add_argument('--diary', help='organize gallery using markdown file diary',
                        action='store', default='false', choices=BOOL)
    agroup.add_argument('--recursive', help='--sourcedir scans recursively',
                        action='store', default='false', choices=BOOL)
    agroup.add_argument('--dates', help='dates interval for extended index',
                        action='store', default='source')
    agroup.add_argument('--sourcedir', help='image source for extended index',
                        action='store', default=None)
    agroup.add_argument('--update', help='updates thumbnails with parameters in config file',
                        action='store_true', default=False)
    agroup.add_argument('--dest', help='output directory',
                        action='store')
    agroup.add_argument('--forcethumb', help='force calculation of thumbnails',
                        action='store_true', default=False)

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

    args.root = (
        args.create or args.gallery
        or args.blogger or args.idem or args.resetcfg
    )

    if args.setcfg:
        args.root = args.setcfg[0]
        args.setcfg = args.setcfg[1:]

    return args


def setup_part1(args):
    """
    Made before reading config file (config file located in args.root).
    Check and normalize root path.
    """
    rootext = os.path.splitext(args.root)[1]
    if rootext.lower() in ('.htm', '.html'):
        args.rootname = os.path.basename(args.root)
        args.root = os.path.dirname(args.root)
    else:
        args.rootname = 'index.htm'

    if args.root:
        args.root = os.path.abspath(args.root)
        if not os.path.isdir(args.root):
            if args.gallery:
                os.mkdir(args.root)
            else:
                error('Directory not found', args.root)


def setup_part2(args):
    """
    Made after reading config file.
    Check for ffmpeg in path.
    Create .thumbnails dir if necessary and create .nomedia in it.
    Copy photobox file to destination dir.
    Handle priority between command line and config file.
    """
    if args.sourcedir:
        args.sourcedir = os.path.abspath(args.sourcedir)
        if os.path.splitdrive(args.sourcedir)[0]:
            drive, rest = os.path.splitdrive(args.sourcedir)
            args.sourcedir = drive.upper() + rest
        if not os.path.isdir(args.sourcedir):
            error('Directory not found', args.sourcedir)
    else:
        if args.gallery and args.update is None:
            error('Directory not found', 'Use --sourcedir')

    if args.update:
        args.sourcedir = args.source.sourcedir
        args.bydir = args.source.bydir
        args.bydate = args.source.bydate
        args.diary = args.source.diary
        args.recursive = args.source.recursive
        args.dates = args.source.dates
    elif args.gallery:
        args.source.sourcedir = args.sourcedir
        args.source.bydir = args.bydir
        args.source.bydate = args.bydate
        args.source.diary = args.diary
        args.source.recursive = args.recursive
        args.source.dates = args.dates
        update_config(args)

    if args.dest:
        args.dest = os.path.abspath(args.dest)

    if args.dest is None:
        args.dest = args.root

    if args.blogger and args.urlblogger is None:
        error('No blogger url (--url)')

    if args.gallery:
        # check for ffmpeg and ffprobe in path
        for exe in ('ffmpeg', 'ffprobe'):
            try:
                check_output([exe, '-version'])
            except FileNotFoundError:
                error('File not found', exe)

        args.thumbdir = os.path.join(args.dest, '.thumbnails')
        if not os.path.exists(args.thumbdir):
            os.mkdir(args.thumbdir)
            open(os.path.join(args.thumbdir, '.nomedia'), 'a').close()

        favicondst = os.path.join(args.dest, 'favicon.ico')
        if not os.path.isfile(favicondst):
            faviconsrc = os.path.join(os.path.dirname(__file__), 'favicon.ico')
            shutil.copyfile(faviconsrc, favicondst)

        photoboxdir = os.path.join(args.dest, 'photobox')
        if not os.path.exists(photoboxdir):
            photoboxsrc = os.path.join(os.path.dirname(__file__), 'photobox')
            shutil.copytree(photoboxsrc, photoboxdir)

    args.bydir = args.bydir is True or args.bydir == 'true'
    args.bydate = args.bydate is True or args.bydate == 'true'
    args.diary = args.diary is True or args.diary == 'true'
    args.recursive = args.recursive is True or args.recursive == 'true'

    if args.dates:
        if not(args.gallery or args.create):
            # silently ignored for the moment, otherwise all other commands will
            # launch a wanrning or an error on the default --dates value
            pass

        if args.dates == 'source':
            pass
        elif args.dates == 'diary':
            if args.create:
                error('Incorrect date format', args.dates)
        elif re.match(r'\d+-\d+', args.dates):
            date1, date2 = args.dates.split('-')
            if validate_date(date1) and validate_date(date2):
                args.dates = date1, date2
            else:
                error('Incorrect date format', args.dates)
        else:
            error('Incorrect date format', args.dates)


def validate_date(datestr):
    # datestr = yyyymmdd
    try:
        datetime.datetime.strptime(datestr, '%Y%m%d')
        return True
    except ValueError:
        return False


def main(argstring=None):
    colorama.init()
    locale.setlocale(locale.LC_TIME, '')
    args = parse_command_line(argstring)
    setup_part1(args)
    read_config(args)
    setup_part2(args)
    try:
        if args.create:
            create_diary(args)

        elif args.gallery:
            create_gallery(args)

        elif args.blogger:
            prepare_for_blogger(args)

        elif args.idem:
            idempotence(args)

        elif args.setcfg:
            setconfig_cmd(args)

        elif args.test:
            pass
    except KeyboardInterrupt:
        warning('Interrupted by user.')


if __name__ == '__main__':
    main()
