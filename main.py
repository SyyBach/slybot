#!/usr/bin/python3

import discord
from discord.ext import commands
import asyncio
#from concurrent.futures import CancelledError

#from json import load as jsonloadfile
#from gc import collect as gc_collect
#from os import makedirs
#from os.path import exists as path_exists, dirname

#from random import randrange
#from math import exp

import logging
# create root logger
logger = logging.getLogger("main")
# create console handler and set level to debug
c_handler = logging.StreamHandler()
c_handler.setLevel(logging.INFO)
#handler=None    #declare global variable
# make formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s:%(name)s: %(message)s')
c_handler.setFormatter( formatter )

# perform assignment
logger.addHandler(c_handler)



import trivia
import chat
import rpg
import my_maths



def main(token):
    description="Slyfer11's bot"
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('./'), description=description)

    #bot.add_cog(trivia.TriviaManager(bot))
    bot.add_cog(chat.ChatCommands(bot))
    bot.add_cog(rpg.RPGCommands(bot))
    bot.add_cog(my_maths.MathsCog(bot))

    @bot.event
    @asyncio.coroutine
    def on_ready():
        print('Logged in as')
        print(bot.user.name)
        print(bot.user.id)
        print('------')


    #initialize questionPool
    #trivia.QC_Manager.simple_eq = True
    #trivia.QuestionPool()
    #trivia.QC_Manager.simple_eq = False


    bot.run(token)


if __name__=="__main__":
    from sys import argv
    import getopt

    
    #connection tokens
    live_token="MjQ1NjkyNDk5MzEyNjQwMDAw.CwPyfA.Xx3WuuLf8Qx5q-ggJs51dgjq7JY"
    beta_token="MjQ1MzEyMTk3NjYyNzM2Mzg0.CwKVGw.Xz_Dl20jRwyU69YG44lP5Yui4Hw"



    try:
        opts, args = getopt.getopt(argv[1:],"bl",["beta","live"])
    except getopt.GetoptError:
        #print 'test.py -i <inputfile> -o <outputfile>'
        print("Wrong usage")
        sys.exit(2)


    for opt, arg in opts:
        if opt in ("-b","--beta"):
            logger.setLevel(logging.DEBUG)
            # make file handler
            handler = logging.FileHandler(filename='log/beta/__main__.log', encoding='utf-8')    #mode should default to 'a'
            handler.setLevel(logging.DEBUG)

            token= beta_token
            print("Bot will run on beta token!")
        else:
            logger.setLevel(logging.INFO)
            # make file handler
            handler = logging.FileHandler(filename='log/__main__.log', encoding='utf-8')    #mode should default to 'a'
            handler.setLevel(logging.DEBUG)

            token= live_token
            print("Bot will run on live token!")


    handler.setFormatter( formatter )
    logger.addHandler(handler)


    main(token)
