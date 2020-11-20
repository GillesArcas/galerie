import os
import sys
import inspect
import shutil
import glob
import clipboard
import journal


def list_compare(tag1, tag2, list1, list2):

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
        for line in diff[:10]:
            print(line)

    return res


def file_compare(fn1, fn2):
    with open(fn1) as f:
        lines1 = [line.strip('\n') for line in f.readlines()]
    with open(fn2) as f:
        lines2 = [line.strip('\n') for line in f.readlines()]
    return list_compare(fn1, fn2, lines1, lines2)


def directory_compare(dir1, dir2):
    list1 = os.listdir(dir1)
    list2 = os.listdir(dir2)
    return list_compare(dir1, dir2, list1, list2)


def test_01_idem(mode):
    # test number to keep test order
    if mode == 'ref':
        return None
    else:
        journal.main('--idem --in ./ --out tmp')
        return file_compare('index.md', 'tmp/index.md')


def test_01_idem_no_md_file(mode):
    try:
        journal.main('--idem --in ./no_md_file')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('File not found')


def test_02_html(mode):
    if mode == 'ref':
        journal.main('--html --in ./ --out .')
        return None
    else:
        journal.main('--html --in ./ --out tmp')
        return file_compare('index.htm', 'tmp/index.htm')


def test_02_html_no_md_file(mode):
    try:
        journal.main('--html --in ./no_md_file')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('File not found')


def test_03_ext(mode):
    if mode == 'ref':
        journal.main('--extend --in ./ --out . --imgs . --flat')
        os.rename('index-x.htm', 'index-x-base.htm')
        return None
    else:
        journal.main('--extend --in ./ --out tmp --imgs . --flat')
        return file_compare('index-x-base.htm', 'tmp/index-x.htm')


def test_03_ext_dates(mode):
    if mode == 'ref':
        journal.main('--extend --in ./ --out . --imgs . --flat --dates 20000101-20000110')
        os.rename('index-x.htm', 'index-x-dates.htm')
        return None
    else:
        journal.main('--extend --in ./ --out tmp --imgs . --flat --dates 20000101-20000110')
        return (
            file_compare('index-x-dates.htm', 'tmp/index-x.htm') and
            # .thumbnails is tested after the last command modifying thumbnails
            directory_compare('.thumbnails', 'tmp/.thumbnails')
            )


def test_03_ext_no_md_file(mode):
    if mode == 'ref':
        journal.main('--extend --in no_md_file --out no_md_file --imgs . --flat --dates 20000101-20000110')
        return None
    else:
        journal.main('--extend --in no_md_file --out tmp --imgs . --flat --dates 20000101-20000110')
        return (
            directory_compare('no_md_file/.thumbnails', 'tmp/.thumbnails') and
            file_compare('no_md_file/index-x.htm', 'tmp/index-x.htm')
            )


def test_create(mode):
    journal.main('--create --out tmp --imgs . --flat')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'index-create-base.md')
    else:
        return file_compare('index-create-base.md', 'tmp/index.md')


def test_create_date(mode):
    journal.main('--create --out tmp --imgs . --flat --dates 20000101-20000110')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'index-create-dates.md')
    else:
        return file_compare('index-create-dates.md', 'tmp/index.md')


def test_blogger(mode):
    journal.main('--blogger --in ./ --url blogger-medias.htm --check')
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
        journal.main('--html --in foobar --out .')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('Directory not found')


def test_dir_imgsource_not_given(mode):
    try:
        journal.main('--extend --in ./ --out .')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('No image source (--imgsource)')


def test_dir_imgsource_not_found(mode):
    try:
        journal.main('--extend --in ./ --out . --imgs foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('Directory not found')


def test_url_blogger_not_given(mode):
    try:
        journal.main('--blogger --in ./')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('No blogger url (--url)')


def test_url_blogger_not_read(mode):
    try:
        journal.main('--blogger --in ./ --url foobar')
        return False
    except SystemExit as exception:
        return exception.args[0] == journal.errorcode('Unable to read url')


def testfunctions():
    return [(name, obj) for name, obj in inspect.getmembers(sys.modules[__name__])
                if (inspect.isfunction(obj) and name.startswith('test_'))]


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
            print(f'Test: {name}')
            test('ref')
        shutil.rmtree('tmp')
    else:
        nbtest = len(testfunctions())
        nbcorrect = 0
        for name, test in testfunctions():
            print(f'Test: {name}')
            nbcorrect += test('go')

        if nbcorrect == nbtest:
            print('All tests ok (%d/%d)' % (nbcorrect, nbtest))
            shutil.rmtree('tmp')
            sys.exit(0)
        else:
            print('Test failure (%d/%d)' % (nbcorrect, nbtest))
            sys.exit(1)


main()
