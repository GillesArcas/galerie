import os
import sys
import inspect
import shutil
import glob
import colorama
import clipboard
import journal


# -- Helpers ------------------------------------------------------------------


def list_compare(tag1, tag2, list1, list2, source1='<list1>', source2='<list2>'):

    # make sure both lists have same length
    maxlen = max(len(list1), len(list2))
    list1.extend([''] * (maxlen - len(list1)))
    list2.extend([''] * (maxlen - len(list2)))

    diff = list()
    res = True
    for i, (x, y) in enumerate(zip(list1, list2)):
        if x != y:
            diff.append('line %s %d: %s' % (tag1, i + 1, x))
            diff.append('line %s %d: %s' % (tag2, i + 1, y))
            res = False

    if diff:
        print(colorama.Fore.RED)
        print('Diff:', tag1, source1, tag2, source2)
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


# -- Tests --------------------------------------------------------------------


def test_00_Config_00(mode):
    if mode == 'ref':
        journal.main('--resetcfg gallery')
        journal.main('--gallery gallery --imgs subdir')
        shutil.copyfile('gallery/index-x.htm', 'gallery/index-config1.htm')
        return None
    else:
        journal.main('--resetcfg tmp')
        journal.main('--gallery tmp --imgs subdir')
        return file_compare('gallery/index-config1.htm', 'tmp/index-x.htm')


def test_00_Config_01(mode):
    if mode == 'ref':
        journal.setconfig('gallery/.config.ini', 'thumbnails', 'subdir_caption', 'False')
        journal.setconfig('gallery/.config.ini', 'photobox', 'loop', 'True')
        journal.setconfig('gallery/.config.ini', 'photobox', 'time', '2000')
        journal.main('--gallery gallery --imgs subdir')
        os.remove('gallery/.config.ini')
        shutil.copyfile('gallery/index-x.htm', 'gallery/index-config2.htm')
        return None
    else:
        journal.setconfig('tmp/.config.ini', 'thumbnails', 'subdir_caption', 'False')
        journal.setconfig('tmp/.config.ini', 'photobox', 'loop', 'True')
        journal.setconfig('tmp/.config.ini', 'photobox', 'time', '2000')
        journal.main('--gallery tmp --imgs subdir')
        return file_compare('gallery/index-config2.htm', 'tmp/index-x.htm')


def test_00_Config_02(mode):
    if mode == 'ref':
        return None
    else:
        try:
            journal.setconfig('tmp/.config.ini', 'photobox', 'loop', 'foobar')
            journal.main('--gallery tmp --imgs subdir/deeper1')
            return False
        except SystemExit as exception:
            return exception.args[0] == journal.errorcode('missing or incorrect config value:')
        finally:
            journal.setconfig('tmp/.config.ini', 'photobox', 'loop', 'false')


def test_00_Config_03(mode):
    if mode == 'ref':
        return None
    else:
        try:
            journal.setconfig('tmp/.config.ini', 'photobox', 'time', 'abc')
            journal.main('--gallery tmp --imgs subdir/deeper1')
            return False
        except SystemExit as exception:
            return exception.args[0] == journal.errorcode('missing or incorrect config value:')
        finally:
            journal.setconfig('tmp/.config.ini', 'photobox', 'time', '3000')


def test_01_idem(mode):
    # test number to keep test order
    if mode == 'ref':
        return None
    else:
        journal.main('--idem . --dest tmp')
        return file_compare('index.md', 'tmp/index.md')


def test_01_idem_no_md_file(mode):
    try:
        journal.main('--resetcfg no_md_file')
        journal.main('--idem no_md_file')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('File not found')


def test_02_html(mode):
    if mode == 'ref':
        journal.main('--resetcfg .')
        journal.main('--html .')
        return None
    else:
        journal.main('--resetcfg .')
        journal.main('--html . --dest tmp')
        return file_compare('index.htm', 'tmp/index.htm')


def test_02_html_no_md_file(mode):
    try:
        journal.main('--html no_md_file')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('File not found')


def test_03_ext(mode):
    if mode == 'ref':
        journal.main('--extend . --imgs . --flat')
        os.rename('index-x.htm', 'index-x-base.htm')
        return None
    else:
        journal.main('--extend . --dest tmp --imgs . --flat')
        return file_compare('index-x-base.htm', 'tmp/index-x.htm')


def test_03_ext_dates(mode):
    if mode == 'ref':
        journal.main('--extend . --imgs . --flat --dates 20000101-20000110')
        os.rename('index-x.htm', 'index-x-dates.htm')
        return None
    else:
        journal.main('--extend . --dest tmp --imgs . --flat --dates 20000101-20000110')
        return file_compare('index-x-dates.htm', 'tmp/index-x.htm')


def test_03_ext_rec(mode):
    if mode == 'ref':
        journal.main('--extend . --imgs . --rec')
        os.rename('index-x.htm', 'index-x-rec.htm')
        return None
    else:
        journal.main('--extend . --dest tmp --imgs . --rec')
        return file_compare('index-x-rec.htm', 'tmp/index-x.htm')
        return (
            file_compare('index-x-rec.htm', 'tmp/index-x.htm') and
            # .thumbnails is tested after the last command modifying thumbnails
            directory_compare('.thumbnails', 'tmp/.thumbnails')
        )


def test_04_ext_no_md_file(mode):
    if mode == 'ref':
        journal.main('--extend no_md_file --imgs . --flat --dates 20000101-20000110')
        return None
    else:
        journal.main('--extend no_md_file --dest tmp --imgs . --flat --dates 20000101-20000110')
        return (
            directory_compare('no_md_file/.thumbnails', 'tmp/.thumbnails') and
            file_compare('no_md_file/index-x.htm', 'tmp/index-x.htm')
        )


def test_gallery(mode):
    if mode == 'ref':
        journal.main('--resetcfg gallery')
        journal.main('--gallery gallery --imgs .')
        shutil.copyfile('gallery/index-x.htm', 'gallery/index-gallery.htm')
        return None
    else:
        journal.main('--resetcfg tmp')
        journal.main('--gallery tmp --imgs .')
        return (
            directory_compare('gallery/.thumbnails', 'tmp/.thumbnails')
            and file_compare('gallery/index-gallery.htm', 'tmp/index-x.htm')
            and file_compare('gallery/subdir.htm', 'tmp/subdir.htm')
            and file_compare('gallery/subdir_deeper1.htm', 'tmp/subdir_deeper1.htm')
            and file_compare('gallery/subdir_deeper2.htm', 'tmp/subdir_deeper2.htm')
            and file_compare('gallery/subdir_deeper2_deepest.htm', 'tmp/subdir_deeper2_deepest.htm')
        )


def test_create(mode):
    journal.main('--create tmp --imgs . --flat')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'index-create-base.md')
    else:
        return file_compare('index-create-base.md', 'tmp/index.md')


def test_create_date(mode):
    journal.main('--create tmp --imgs . --flat --dates 20000101-20000110')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'index-create-dates.md')
    else:
        return file_compare('index-create-dates.md', 'tmp/index.md')


def test_blogger(mode):
    journal.main('--blogger . --url blogger-medias.htm --check')
    if mode == 'ref':
        with open('blogger-output.htm', 'wt') as f:
            f.write(clipboard.paste())
        return None
    else:
        with open('tmp/blogger-output.htm', 'wt') as f:
            f.write(clipboard.paste())
        return file_compare('blogger-output.htm', 'tmp/blogger-output.htm')


def test_dir_input_not_found(mode):
    try:
        journal.main('--html foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('Directory not found')


def test_dir_imgsource_not_given(mode):
    try:
        journal.main('--extend .')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('No image source (--imgsource)')


def test_dir_imgsource_not_found(mode):
    try:
        journal.main('--extend . --imgs foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('Directory not found')


def test_url_blogger_not_given(mode):
    try:
        journal.main('--blogger .')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('No blogger url (--url)')


def test_url_blogger_not_read(mode):
    try:
        journal.main('--blogger . --url foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('Unable to read url')


def testfunctions():
    return [(name, obj) for name, obj in inspect.getmembers(sys.modules[__name__])
                if (inspect.isfunction(obj) and name.startswith('test_'))]


# -- Main ---------------------------------------------------------------------


def main():
    if sys.argv[1:] and sys.argv[1] == 'ref':
        mode = 'ref'
    else:
        mode = 'test'

    if os.path.exists('tmp'):
        shutil.rmtree('tmp')
    os.mkdir('tmp')

    if mode == 'ref':
        for fn in glob.glob('index*.*'):
            if fn != 'index.md':
                os.remove(fn)
        for name, test in testfunctions():
            print(f'{colorama.Fore.YELLOW}Test: {name}{colorama.Style.RESET_ALL}')
            test('ref')
        shutil.rmtree('tmp')
    else:
        nbtest = len(testfunctions())
        nbcorrect = 0
        for name, test in testfunctions():
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
main()
