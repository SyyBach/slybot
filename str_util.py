"""This module provides utilities for comparing strings. Currently only provide methods based on the Damerau-Levenshtein distance"""

import logging
loc_log = logging.getLogger("main.str_util")
from math import exp

alphabet="abcdefghijklmnopqrstuvwxyz0123456789 "
upper="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ignore=",'\".:;/-?%!$&()[]"
special="_*"


def Damerau_Levenshtein_dist(a,b):
    """Computes the true Damerau–Levenshtein distance between strings a and b, algorithm from wikipedia. The method assumes all character are in a-z0-9, thus capital letters and other symbols MUST be removed beforehand. Space characters are also accepted, but trailing/leading/multiple spaces should be removed."""

    da = { x:0 for x in alphabet }

    d = [ [ 0 for y in range(len(b)+2) ] for x in range( len(a)+2 ) ]

    maxdist= len(a) + len(b)
    d[0][0] = maxdist
    for i in range( 1, len(a)+2 ):
        d[i][0] = maxdist
        d[i][1] = i-1
    for j in range( 1, len(b)+2 ):
        d[0][j] = maxdist
        d[1][j] = j-1

    # Note:
    # when used for a/b arrays, indices i and j are in advance by 2     (need -2)
    # when used for d[][], i and j can be used as is                    (+/- 0)
    # when used as "cost" values, i and j are in advance by 1           (need -1)
    #
    # da is dictionary, so no index adjustment for its keys
    # da and db are "cost" values from the wiki algo, they are never used directly, but indirectly through k and l
    # when used for a/b arrays, k and l are in advance by 1             (need -1)
    # when used for d[][], k and l are late by 1                        (need +1)
    for i in range( 2, len(a)+2 ):
        db=0
        for j in range( 2, len(b)+2 ):
            k=da[ b[j-2] ]  #k is a "cost" value and must be index-adjusted
            l=db            #l is a "cost" value and must be index-adjusted
            if a[i-2] == b[j-2]:
                cost = 0
                db = j-1    #db must be adjusted as a "cost" value
            else:
                cost = 1

            d[i][j] = min( d[i-1][j-1] + cost,
                            d[i][j-1] + 1,
                            d[i-1][j] + 1,
                            d[k+1-1][l+1-1] + (i-1-k-1) + 1 + (j-1-l-1))

        da[ a[i-2] ] = i-1  #da must be adjusted as a "cost" value

    return d[ len(a)+1 ][ len(b)+1 ]


def clean_str(inStr, *, lowercase=True, remove_symbols=True, remove_special=True, DL_dist=False):
    loc_log.debug("clean_str invoked on string:'{}' with arguments lowercase={}, remove_symbols={}, remove_special={}, DL_dist={}".format(inStr,lowercase,remove_symbols,remove_special,DL_dist))
    #flag management
    if DL_dist:
        remove_symbols=True
        remove_special=True
    
    remove=""
    if remove_symbols:
        remove+=ignore
    if remove_special:
        remove+=special

    #lowervase processing should go among the first
    if lowercase:
        inStr=inStr.lower()
        work_alphabet=alphabet
    else:
        work_alphabet=alphabet+upper
    #eliminate spurious whitespace
    inStr = inStr.split()

    #loop over words and remove character if requested
    if len(remove)>0:
        for idx,word in enumerate(inStr):
            word=list(word)
            for idx_word,c in enumerate(word):
                if c in remove or (DL_dist and not c in work_alphabet):
                    word[idx_word] = ""
                
            inStr[idx]="".join(word)

    return " ".join(inStr)


def adaptative_strictness(len1,len2=None):
    if len2 == None:    #make sure len2==0 does not pass through
        worklen=len1
    else:
        worklen=min(len1,len2)
    if worklen <= 0:
        print("Question.adaptive_strictness: negative lengths were passed, silently proceeding")

    if worklen <= 9:
        return 0
    elif worklen <= 14:
        return 1
    elif worklen <= 19:
        return 2
    elif worklen <= 22:
        return 3
    else:
        return int( exp( worklen/14. ) -1 )


def similar_string_test(str1,str2):
    loc_log.debug("similar_string_test invoked on strings '{}' and '{}'".format(str1,str2))
    dl_dist=Damerau_Levenshtein_dist( clean_str(str1,DL_dist=True), clean_str(str2,DL_dist=True) )
    return dl_dist <= adaptative_strictness(len(str1),len(str2))


