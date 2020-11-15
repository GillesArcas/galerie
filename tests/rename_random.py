import os
import glob
import random

#        1  2  3  4  5  6  7  8  9 10
MD = (0, 1, 0, 0, 2, 1, 1, 3, 2, 0, 0)

while 1:
    dates = [list() for _ in range(11)]
    for image in glob.glob('*.jpg'):
        dates[random.randint(1, 10)].append(image)
    if all(len(images) >= MD[date] for date, images in enumerate(dates)):
        break

for date, images in enumerate(dates):
    for rank, image in enumerate(images):
        newname = f'OCT_200001{date:02}_0000{rank:02}.jpg'
        print(date, rank, image, newname)
        os.rename(image, newname)
