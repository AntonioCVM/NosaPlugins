# -*- coding: utf-8 -*-
"""
CPython with PyMuPDF: the first page of each named PDF of a run rendered to PNG, for checkpoint evidence.
Usage: python pdf_captures.py <pdf folder> <out folder> <dpi> <sheet number> [...]
"""
import glob
import os
import sys

import fitz


def main(folder, out, dpi, numbers):
    os.makedirs(out, exist_ok=True)
    for number in numbers:
        found = sorted(glob.glob(os.path.join(folder, number + ' - *.pdf')))
        if not found:
            print('missing', number)
            continue
        page = fitz.open(found[0])[0]
        path = os.path.join(out, os.path.basename(found[0])[:-4] + '.png')
        page.get_pixmap(dpi=dpi).save(path)
        print(path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4:])
