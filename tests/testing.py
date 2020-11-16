import os
import sys
import shutil
import glob
# from journal import main
import clipboard
import journal.journal


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


def test1(mode):
    if mode == 'ref':
        return None
    else:
        journal.journal.main('--idem --in ./ --out tmp')
        return file_compare('index.md', 'tmp/index.md')


def test2(mode):
    if mode == 'ref':
        journal.journal.main('--html --in ./ --out .')
        return None
    else:
        journal.journal.main('--html --in ./ --out tmp')
        return file_compare('index.htm', 'tmp/index.htm')


def test3(mode):
    if mode == 'ref':
        journal.journal.main('--extend --in ./ --out . --imgs . --flat')
        os.rename('index-x.htm', 'index-x-base.htm')
        return None
    else:
        journal.journal.main('--extend --in ./ --out tmp --imgs . --flat')
        return file_compare('index-x-base.htm', 'tmp/index-x.htm')


def test4(mode):
    if mode == 'ref':
        journal.journal.main('--extend --in ./ --out . --imgs . --flat --dates 20000101-20000110')
        os.rename('index-x.htm', 'index-x-dates.htm')
        return None
    else:
        journal.journal.main('--extend --in ./ --out tmp --imgs . --flat --dates 20000101-20000110')
        return (
            file_compare('index-x-dates.htm', 'tmp/index-x.htm') and
            # .thumbnails is tested after the latter command modifying thumbnails
            directory_compare('.thumbnails', 'tmp/.thumbnails')
            )


def test5(mode):
    journal.journal.main('--create --out tmp --imgs . --flat')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'index-create-base.md')
    else:
        return file_compare('index-create-base.md', 'tmp/index.md')


def test6(mode):
    journal.journal.main('--create --out tmp --imgs . --flat --dates 20000101-20000110')
    if mode == 'ref':
        return shutil.copyfile('tmp/index.md', 'index-create-dates.md')
    else:
        return file_compare('index-create-dates.md', 'tmp/index.md')


def test7(mode):
    journal.journal.main('--blogger --in ./ --url blogger-medias.htm')
    if mode == 'ref':
        with open('blogger-output.htm', 'wt') as f:
            f.write(clipboard.paste())
        return None
    else:
        with open('tmp/blogger-output.htm', 'wt') as f:
            f.write(clipboard.paste())
        return file_compare('blogger-output.htm', 'tmp/blogger-output.htm')


TESTLIST = [test1, test2, test3, test4, test5, test6, test7]


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
        for idx, test in enumerate(TESTLIST, 1):
            print(f'Test #{idx}')
            test('ref')
        shutil.rmtree('tmp')
    else:
        nbtest = len(TESTLIST)
        nbcorrect = 0
        for idx, test in enumerate(TESTLIST, 1):
            print(f'Test #{idx}')
            nbcorrect += test('go')

        if nbcorrect == len(TESTLIST):
            print('All tests ok')
            shutil.rmtree('tmp')
            sys.exit(0)
        else:
            print('Test failure (%d/%d)' % (nbcorrect, nbtest))
            sys.exit(1)


main()
