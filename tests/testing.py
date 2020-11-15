import os
import sys
# from journal import main
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


def test1():
    journal.journal.main('--idem --in ./ --out tmp')
    return file_compare('index.md', 'tmp/index.md')


def test2():
    journal.journal.main('--html --in ./ --out tmp')
    return (
        file_compare('index.htm', 'tmp/index.htm') and
        directory_compare('.thumbnails', 'tmp/.thumbnails')
    )


def test3():
    journal.journal.main('--extend --in ./ --out tmp --imgs . --flat')
    return (
        file_compare('index-x.htm', 'tmp/index-x.htm') and
        directory_compare('.thumbnails', 'tmp/.thumbnails')
    )


TESTLIST = [test1, test2, test3]


def main():
    if not os.path.exists('tmp'):
        os.mkdir('tmp')

    result = sum(test() for test in TESTLIST)

    if result == len(TESTLIST):
        print('All tests ok')
        sys.exit(0)
    else:
        print('Test failure (failed: %d)' % (len(TESTLIST) - result))
        sys.exit(1)

    # os.remove('tmp')


main()
