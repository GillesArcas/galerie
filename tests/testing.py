import os
import sys
import re
import inspect
import shutil
import glob
import locale
import io

import colorama

import galerie


# -- Helpers ------------------------------------------------------------------


def line_compare(line1, line2):
    return line1 == line2


def line_compare(line1, line2):
    """
    Compare two lines ignoring absolute paths (in html files and md files
    titles). This makes possible the relocalisation of the tests (make the
    reference data in some directory and run the tests somewhere else).
    """
    line1 = re.sub(r'"file:///.*([^/\\]+)"', 'file:///\1"', line1)
    line2 = re.sub(r'"file:///.*([^/\\]+)"', 'file:///\1"', line2)
    if line1 == line2:
        return True

    # tailored specifically for paths in titles of diary files
    line1 = re.sub(r'^# .*([^/\\]+)', '\1', line1)
    line2 = re.sub(r'^# .*([^/\\]+)', '\1', line2)
    return line1 == line2


def list_compare(tag1, tag2, list1, list2, source1='<list1>', source2='<list2>'):

    # make sure both lists have same length
    maxlen = max(len(list1), len(list2))
    list1.extend([''] * (maxlen - len(list1)))
    list2.extend([''] * (maxlen - len(list2)))

    diff = list()
    res = True
    for i, (x, y) in enumerate(zip(list1, list2)):
        if not line_compare(x, y):
            diff.append('line %s %d: %s' % (tag1, i + 1, x))
            diff.append('line %s %d: %s' % (tag2, i + 1, y))
            res = False

    if diff:
        print(colorama.Fore.RED)
        print(f'Diff: {tag1}-{tag2}:', source1, source2)
        for line in diff[:10]:
            print(line)
        print(colorama.Style.RESET_ALL)

    return res


def file_compare(fn1, fn2):
    with open(fn1) as f:
        lines1 = [line.strip('\n') for line in f.readlines()]
    with open(fn2) as f:
        lines2 = [line.strip('\n') for line in f.readlines()]
    return list_compare('ref', 'res', lines1, lines2, fn1, fn2)


def directory_compare(dir1, dir2):
    list1 = os.listdir(dir1)
    list2 = os.listdir(dir2)
    return list_compare('ref', 'res', list1, list2, dir1, dir2)


def testfunctions(pref_testfunctions):
    """
    return all test functions in definition order
    """
    return [(name, obj) for name, obj in globals().items()
            if inspect.isfunction(obj) and name.startswith(pref_testfunctions)]


# -- Tests --------------------------------------------------------------------


def generic_test(mode, keeptmp, refdir, *options):
    refdir = f'reference/{refdir}'
    if not keeptmp:
        if os.path.isdir('tmp'):
            shutil.rmtree('tmp')
        os.makedirs('tmp')

    for option in options:
        galerie.main(option)

    thumbdir = '.thumbnails' if os.path.isdir('tmp/.thumbnails') else 'thumbnails'
    with open('tmp/files.txt', 'wt') as f:
        for fn in sorted(glob.glob('tmp/*.htm*')):
            print(os.path.basename(fn), file=f)
        for fn in sorted(glob.glob(f'tmp/{thumbdir}/*.jpg')):
            print(os.path.basename(fn), file=f)
        for fn in sorted(glob.glob(f'tmp/{thumbdir}/*.info')):
            print(os.path.basename(fn), file=f)

    if mode == 'ref':
        if os.path.isdir(refdir):
            shutil.rmtree(refdir)
        os.makedirs(refdir)
        shutil.copy('tmp/files.txt', refdir)
        for fn in glob.glob('tmp/*.htm*'):
            shutil.copy(fn, refdir)
    else:
        for fn in glob.glob(os.path.join(refdir, '*.*')):
            if file_compare(fn, os.path.join('tmp', os.path.basename(fn))) is False:
                return False
        else:
            return True


def remove_tmp():
    if os.path.isdir('tmp'):
        shutil.rmtree('tmp')


def reset_tmp():
    remove_tmp()
    os.makedirs('tmp')


def populate_tmp():
    reset_tmp()
    shutil.copyfile('index.md', os.path.join('tmp/index.md'))
    for basename in glob.glob('VID*.mp4'):
        shutil.copyfile(basename, os.path.join('tmp', basename))
    for basename in glob.glob('OCT*.jpg'):
        shutil.copyfile(basename, os.path.join('tmp', basename))


def test_18_gallery(mode):
    # create gallery when not existing
    remove_tmp()
    return generic_test(
        mode,
        True,
        'test_18_gallery',
        '--gallery tmp --source .'
        )


def test_00_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_00_gallery',
        '--gallery tmp --source . --bydir false --bydate false --recursive false'
        )


def test_00_gallery_with_dates(mode):
    return generic_test(
        mode,
        False,
        'test_00_gallery_with_dates',
        '--gallery tmp --source . --bydir false --bydate false --recursive false --dates 20000105-20000108'
        )


def test_01_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_01_gallery',
        '--gallery tmp --source . --bydir false --bydate false --recursive true'
        )


def test_01_gallery_with_dates(mode):
    return generic_test(
        mode,
        False,
        'test_01_gallery_with_dates',
        '--gallery tmp --source . --bydir false --bydate false --recursive true --dates 20000105-20000108'
        )


def test_02_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_02_gallery',
        '--gallery tmp --source . --bydir false --bydate true --recursive false'
        )


def test_03_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_03_gallery',
        '--gallery tmp --source . --bydir false --bydate true --recursive true'
        )


def test_04_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_04_gallery',
        '--gallery tmp --source . --bydir true --bydate false'
        )


def test_04_gallery_with_dates(mode):
    return generic_test(
        mode,
        False,
        'test_04_gallery_with_dates',
        '--gallery tmp --source . --bydir true --bydate false --dates 20000105-20000108'
        )


def test_05_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_05_gallery',
        '--gallery tmp --source . --bydir true --bydate true'
        )


def test_16_gallery(mode):
    # test --update
    reset_tmp()
    galerie.main('--gallery tmp --source . --bydir true --bydate true')
    os.rename('OCT_20000101_000000.jpg', 'TOC_20000101_000000.jpg')
    try:
        return generic_test(
            mode,
            True,
            'test_16_gallery',
            '--gallery tmp --update'
            )
    finally:
        os.rename('TOC_20000101_000000.jpg', 'OCT_20000101_000000.jpg')


def test_update_incorrect_parameter(mode):
    # test --update with incorrect parameter
    reset_tmp()
    try:
        galerie.main('--gallery tmp --update --bydir true')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Incorrect parameters:')


def test_21_gallery(mode):
    # test thumbnail purge below threshold
    reset_tmp()
    galerie.main('--gallery tmp --source . --bydate true --dates source')
    return generic_test(
        mode,
        True,
        'test_21_gallery',
        '--gallery tmp --source . --bydate true --dates 20000101-20000107'
        )


def test_22_gallery(mode):
    # test thumbnail purge above threshold and accept removing
    reset_tmp()
    galerie.main('--gallery tmp --source . --bydate true --dates source')
    try:
        stdin = sys.stdin
        sys.stdin = io.StringIO('x\nx\ny')
        return generic_test(
            mode,
            True,
            'test_22_gallery',
            '--gallery tmp --source . --bydate true --dates 20000101-20000102'
            )
    finally:
        sys.stdin = stdin


def test_23_gallery(mode):
    # test thumbnail purge above threshold and deny removing
    reset_tmp()
    galerie.main('--gallery tmp --source . --bydate true --dates source')
    try:
        stdin = sys.stdin
        sys.stdin = io.StringIO('x\nx\nn')
        return generic_test(
            mode,
            True,
            'test_23_gallery',
            '--gallery tmp --source . --bydate true --dates 20000101-20000102'
            )
    finally:
        sys.stdin = stdin


def test_06_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_06_gallery',
        '--gallery tmp --source . --bydir true --bydate true --dates 20000103-20000109'
        )


def test_07_gallery(mode):
    # test diary file not found
    reset_tmp()
    try:
        galerie.main('--gallery tmp --diary true')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('File not found')


def test_14_gallery(mode):
    # test image source not found
    try:
        galerie.main('--gallery tmp --source foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Directory not found')


def test_diary_date_missing(mode):
    # test for date missing in diary
    reset_tmp()
    diary = '''\

______
    '''
    with open('tmp/index.md', 'wt') as f:
        f.write(diary)

    try:
        galerie.main('--gallery tmp --diary true')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('No date in post')


def test_diary_date_incorrect(mode):
    # test for incorrect date in diary
    reset_tmp()
    diary = '''\
[2020/02/30]
______
    '''
    with open('tmp/index.md', 'wt') as f:
        f.write(diary)

    try:
        galerie.main('--gallery tmp --diary true')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Incorrect date value:')


def test_diary_dates_not_ordered(mode):
    # test for post not ordered by dates in diary
    reset_tmp()
    diary = '''\
[2020/01/02]
______
[2020/01/01]
______
    '''
    with open('tmp/index.md', 'wt') as f:
        f.write(diary)

    try:
        galerie.main('--gallery tmp --diary true')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Posts are not ordered')


def test_15_gallery(mode):
    if mode == 'ref':
        return None
    else:
        populate_tmp()
        galerie.createconfig('tmp/.config.ini')
        galerie.setconfig('tmp/.config.ini', 'photobox', 'time', 'abc')
        try:
            galerie.main('--gallery tmp --source subdir/deeper1 --bydir true')
            return False
        except SystemExit as exception:
            return exception.args[0] == galerie.errorcode('Missing or incorrect config value:')


def test_08_gallery(mode):
    return generic_test(
        mode,
        False,
        'test_08_gallery',
        '--resetcfg tmp',
        '--setcfg tmp thumbnails media_description false',
        '--setcfg tmp thumbnails subdir_caption false',
        '--setcfg tmp photobox loop true',
        '--setcfg tmp photobox time 2000',
        '--gallery tmp --source . --bydir true --bydate true'
        )


def test_09_gallery(mode):
    # convert diary file to html without any extra images
    populate_tmp()
    return generic_test(
        mode,
        True,
        'test_09_gallery',
        '--gallery tmp --diary true'
    )


def test_10_gallery(mode):
    # convert diary file to html adding images from sourcedir at dates of diary
    populate_tmp()
    return generic_test(
        mode,
        True,
        'test_10_gallery',
        '--gallery tmp --diary true --source . --dates diary'
    )


def test_11_gallery(mode):
    # convert diary file to html adding images from sourcedir for all dates from source
    populate_tmp()
    return generic_test(
        mode,
        True,
        'test_11_gallery',
        '--gallery tmp --diary true --source .'
    )


def test_12_gallery(mode):
    # convert diary file to html adding images from sourcedir for a selection of dates
    populate_tmp()
    return generic_test(
        mode,
        True,
        'test_12_gallery',
        '--gallery tmp --diary true --source . --dates 20000101-20000105'
    )


def test_13_gallery(mode):
    # convert diary file to html adding images from sourcedir at dates of diary
    populate_tmp()
    return generic_test(
        mode,
        True,
        'test_13_gallery',
        '--gallery tmp --diary true --source subdir --dates source  --recursive true'
    )


def test_gitpages(mode):
    # create gallery compatible with github pages
    reset_tmp()
    return generic_test(
        mode,
        True,
        'test_gitpages',
        '--gallery tmp --source . --bydir true --github_pages true'
    )


def test_17_gallery(mode):
    # create gallery with a name different from default
    populate_tmp()
    return generic_test(
        mode,
        True,
        'test_17_gallery',
        '--gallery tmp/gallery.htm --source .'
    )


def test_diary_file_idempotence(mode):
    reset_tmp()
    if mode == 'ref':
        return None
    else:
        galerie.main('--idem . --dest tmp')
        return file_compare('index.md', 'tmp/index.md')


def test_idempotence_no_md_file(mode):
    reset_tmp()
    try:
        galerie.main('--idem tmp')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('File not found')


def test_create(mode):
    # test diary file creation
    reset_tmp()
    galerie.main('--create tmp --source . ')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'reference/index-create-base.md')
    else:
        return file_compare('reference/index-create-base.md', 'tmp/index.md')


def test_create_date(mode):
    # test diary file creation with date range
    reset_tmp()
    galerie.main('--create tmp --source . --dates 20000101-20000110')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'reference/index-create-dates.md')
    else:
        return file_compare('reference/index-create-dates.md', 'tmp/index.md')


def test_dates_1(mode):
    try:
        galerie.main('--gallery tmp --dates 20200230-20201231')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Incorrect date format')


def test_dates_2(mode):
    try:
        galerie.main('--gallery tmp --dates foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Incorrect date format')


def test_dates_3(mode):
    try:
        galerie.main('--create tmp --dates diary')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Incorrect date format')


def test_blogger(mode):
    reset_tmp()
    if mode == 'ref':
        galerie.main('--blogger . --url blogger-medias.htm --check --dest reference/blogger-output.htm')
        return None
    else:
        galerie.main('--blogger . --url blogger-medias.htm --check --dest tmp/blogger-output.htm')
        return file_compare('reference/blogger-output.htm', 'tmp/blogger-output.htm')


def test_blogger_url_not_given(mode):
    try:
        galerie.main('--blogger .')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('No blogger url (--url)')


def test_blogger_url_not_read(mode):
    try:
        galerie.main('--blogger . --url foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == galerie.errorcode('Unable to read url')


# -- Main ---------------------------------------------------------------------


def main():
    locale.setlocale(locale.LC_TIME, ('fr', 'utf-8'))

    pref_testfunctions = 'test_'
    if sys.argv[1:] and sys.argv[1] == 'ref':
        mode = 'ref'
        if sys.argv[2:]:
            pref_testfunctions = sys.argv[2]
    else:
        mode = 'test'
        if sys.argv[1:] and sys.argv[1] != 'abort':
            pref_testfunctions = sys.argv[1]

    if os.path.exists('tmp'):
        shutil.rmtree('tmp')
    os.mkdir('tmp')

    if mode == 'ref':
        for name, test in testfunctions(pref_testfunctions):
            print(f'{colorama.Fore.YELLOW}Test: {name}{colorama.Style.RESET_ALL}')
            test('ref')
        shutil.rmtree('tmp')
    else:
        nbtest = len(testfunctions(pref_testfunctions))
        nbcorrect = 0
        for name, test in testfunctions(pref_testfunctions):
            print(f'{colorama.Fore.YELLOW}Test: {name}{colorama.Style.RESET_ALL}')
            if test('go'):
                nbcorrect += 1
            elif sys.argv[1:] and sys.argv[1] == 'abort':
                break

        if nbcorrect == nbtest:
            print(colorama.Fore.GREEN + colorama.Style.BRIGHT +
                  'All tests ok (%d/%d)' % (nbcorrect, nbtest),
                  colorama.Style.RESET_ALL)
            shutil.rmtree('tmp')
            sys.exit(0)
        else:
            print('Test failure (%d/%d)' % (nbcorrect, nbtest))
            sys.exit(1)


colorama.init()
try:
    current_path = os.path.abspath(os.getcwd())
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    main()
finally:
    os.chdir(current_path)
