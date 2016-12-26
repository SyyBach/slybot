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
loc_log = logging.getLogger('main.chat')

import re

spoil_re=re.compile("spoil", re.I)


class CooldownManager:
    """Ideally, this guy should be either a singleton, or a static instance in the context it gets instanciated."""
    #TODO use "secure" centralization of clear/set methods? Current implementation bypasses the need to go through _dict

    _dict={}    #only countermeasure to messing around with stuff if singleton-ness not respected
    dict_lock=asyncio.Lock()
    timeout = 5


    def _cd_exists(self,resource_key,caller_key=None):
        """Internal stuff to check on existence of keys. Read only, so no lock logic necessary."""
        return CooldownManager._dict.get(caller_key) and CooldownManager._dict[caller_key].get(resource_key)
        

    def _get_cd(self,resource_key,caller_key=None):
        """Internal stuff without fail checks."""
        return CooldownManager._dict[caller_key][resource_key]


    @asyncio.coroutine
    def _prepare_key(self,resource_key,caller_key=None):
        """...internal stuff, didn't you guess? Ensures existence of the CD items, aka the event object.
        Returns False if the asyncio.Event object could not be created, including if it already existed."""
        
        yield from CooldownManager.dict_lock.acquire()

        #need to invert the logic on asyncio.Event's flag... We want people to wait/block when our "custom flag" is set
        d=CooldownManager._dict.get( caller_key )
        if not d:
            cd = asyncio.Event()
            cd.set()
            CooldownManager._dict[ caller_key ] = { resource_key : cd }
            CooldownManager.dict_lock.release()
            return True

        resource=d.get( resource_key )
        if not resource:
            cd = asyncio.Event()
            cd.set()
            d[ resource_key ] = cd
            CooldownManager.dict_lock.release()
            return True

        CooldownManager.dict_lock.release()
        return False    #The cd already exists


    #@asyncio.coroutine
    def is_on_cd(self,resource_key,caller_key=None):
        """Returns true only if the specific <resource_key>,<caller_key> was asked to be put on cooldown, and timer didn't complete."""
        #If the specified timer doesn't exist, raise a CooldownManager.CooldownKeyError"""

        if not self._cd_exists(resource_key,caller_key):
            #raise CooldownManager.CooldownKeyError(resource_key,caller_key)
            return False

        #need to invert the logic on asyncio.Event's flag... We want people to wait/block when our "custom flag" is set
        return not self._get_cd( resource_key,caller_key ).is_set()



    @asyncio.coroutine
    def put_on_cd(self, duration, resource_key, caller_key=None):
        """Starts a cooldown countdown for <duration> seconds. Cooldown can be checked on via Boolean only through
        the .is_on_cd command. Each cooldown is identified by a <resource_key>, and an optional <caller_key> may
        be provided if it is necessary to use several cooldowns on the same resource.
        
        If <caller_key> is <None>, the cooldown will be put in the common pool of cooldowns.
        
        If the cooldown specified by the <resource_key>,<caller_key> pair is already on cooldown,
        this method will raise a CooldownManager.OnCooldownError"""


        #make sure the CD exists
        if not self._cd_exists(resource_key,caller_key):
            try:
                #if a timeout occurs here, either pi is overloaded or there was a bug in the programmation of the lock's logic
                tmp = yield from asyncio.wait_for( self._prepare_key(resource_key,caller_key), CooldownManager.timeout )
                if not tmp:
                    #key preparation failed
                    raise CooldownManager.KeyCreationError( resource_key,caller_key )
            except:
                raise


        #if already on CD, raise an error
        if self.is_on_cd(resource_key,caller_key):
            raise CooldownManager.OnCooldownError( resource_key,caller_key )


        #at this point, the key should be valid and point to an asyncio.Event object that is SET
        #reminder: need to invert the logic on asyncio.Event's flag... We want people to wait/block when our "custom flag" is set
        asyncio.async( self.cd_task( duration, self._get_cd(resource_key,caller_key) ) )    #delegate the wait task
        return


    @asyncio.coroutine
    def cd_task(self, duration,  cd):
        yield from CooldownManager.dict_lock.acquire()
        cd.clear()  #clear flag to make people wait
        CooldownManager.dict_lock.release()

        yield from asyncio.sleep(duration)  #sleep for given duration

        yield from CooldownManager.dict_lock.acquire()
        cd.set()    #set flag back to unblock people
        CooldownManager.dict_lock.release()
        return

    
    class OnCooldownError(Exception):
        def __init__(self, resource_key, caller_key=None):
            msg="The specified resource (resource_key={}, caller_key={}) is already on cooldown!".format(resource_key,caller_key)
            super().__init__(self,msg,resource_key,caller_key)


    #class CooldownKeyError(Exception):
    #    def __init__(self, resource_key, caller_key=None):
    #        msg="The specified cooldown (resource_key={}, caller_key={}) does not exist!".format(resource_key,caller_key)
    #        super().__init__(self,msg,resource_key,caller_key)


    class KeyCreationError(Exception):
        def __init__(self, resource_key, caller_key=None):
            msg="The cooldown creation for (resource_key={}, caller_key={}) failed! (You're in trouble)".format(resource_key,caller_key)
            super().__init__(self,msg,resource_key,caller_key)




class ChatCommands:
    """A cog to process chat commands and utilities."""

    CD_Manager=CooldownManager()
    cooldown=60
    timeout=10

    def __init__(self,bot):
        self.bot=bot
        #self.lock=asyncio.Lock()    #"semaphore" for gameDict. It is NOT thread safe, only coroutine safe !!!
        return



    @asyncio.coroutine
    def on_message(self,message):
        if not message.author.bot and spoil_re.search(message.content):
            t=(self.bot,message.author.id)
            if not ChatCommands.CD_Manager.is_on_cd(message.channel, t):
                yield from self.bot.send_message(message.channel, content="Did someone say 'spoil' ?")
                yield from self.CD_Manager.put_on_cd(ChatCommands.cooldown, message.channel, t)
            else:
                #silently ignore the spoil mention, no check whether the underlying event bugged
                print("Spoil mention for channel {} is on cooldown".format(message.channel) )
        return






def main(token):
    description="Slyfer11's bot"
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('./'), description=description)

    bot.add_cog(ChatCommands(bot))

    @bot.event
    @asyncio.coroutine
    def on_ready():
        print('Logged in as')
        print(bot.user.name)
        print(bot.user.id)
        print('------')


    bot.run(token)



if __name__=="__main__":

    import logging
    logger = logging.getLogger('chat')
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(filename='log/chat.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)


    from sys import argv
    import getopt

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
            token= beta_token
        else:
            token= live_token

    main(token)
