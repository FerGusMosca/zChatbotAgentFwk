# !/bin/python3

import math
import os
import random
import re
import sys


#
# Complete the 'encryption' function below.
#
# The function is expected to return a STRING.
# The function accepts STRING s as parameter.
#

def encryption(s):
    filt_s = s.replace(" ", "")

    print(f"{filt_s}")

    L=math.ceil(math.sqrt(len(filt_s)))
    rows = L
    pieces = L
    '''
    if  (len(filt_s) % L) != 0:
        rows += 1
        pieces += 1
    '''

    out_mtrx = [[''] * L for _ in range(rows)]

    start = 0
    for j in range(pieces):
        row_str = filt_s[start:start + pieces]
        i = 0
        for c in row_str:
            out_mtrx[i][j] = c
            i += 1

        start += pieces

    str_final = []
    str_col = ""
    for i in range(rows):
        print(f"row {i} --> {out_mtrx[i]}")
        str_col = "".join(out_mtrx[i])
        print(f"str_col {str_col}")
        str_final.append(str_col)

    final_str = " ".join(str_final)
    print(f"final_str {final_str}")
    return final_str


if __name__ == '__main__':
    #fptr = open(os.environ['OUTPUT_PATH'], 'w')

    #s = input()
    s="iffactsdontfittotheorychangethefacts"
    result = encryption(s)

    print(result)
    #fptr.write(result + '\n')

    #fptr.close()
