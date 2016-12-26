#!/usr/bin/python3

import discord
from discord.ext import commands
import asyncio
#from concurrent.futures import CancelledError

#from json import load as jsonloadfile
#from gc import collect as gc_collect
#from os import makedirs
#from os.path import exists as path_exists, dirname

from random import randrange
#from math import exp

import logging
loc_log = logging.getLogger('main.rpg')

import re
float_str="[+-]?(?:[0-9]*\.)?[0-9]+"
rollMod_str="(?:(?P<modifier>(?:<|>){1,2})(?P<inclusive>=)?\s*(?P<modValue>[+-]?(?:[0-9]*\.)?[0-9]+))?"
# +/- space number space d space number
diceParser=re.compile("\s*(?P<operation>[+-])?\s*(?:(?P<diceNumber>[0-9]*)\s*(?P<isDice>d)\s*)?(?P<value>[0-9]+)",re.I)
diceExp=re.compile("(?P<diceExp>(?:\s*[+-]?\s*(?:[0-9]*\s*d\s*)?[0-9]+)+)\s*"+rollMod_str+"\s*",re.I)
inlineTester=re.compile("(?<![a-z])"+"(?P<diceExp>(?:\s*[+-]?\s*(?:[0-9]*\s*d\s*)?[0-9]+)*\s*"+"[+-]?\s*[0-9]*\s*d\s*[0-9]+"+"(?:\s*[+-]?\s*(?:[0-9]*\s*d\s*)?[0-9]+)*)\s*"+rollMod_str,re.I)



#This guy should be put in some separate file, it is currently a copy-paste of chat.CooldownManager
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



def diceRoll(maxInt):
    return randrange(1,maxInt+1)



def parseAndRollDice(expression):
    #init
    res=0
    minVal=0
    maxVal=0

    #main loop
    for match in diceParser.finditer(expression):

        #retrieve relevant dice info
        value = int( match.group("value") )

        #check if is a dice or constant
        if match.group("isDice"):
            tmp = match.group("diceNumber")
            if tmp:
                diceNumber = int( tmp )
            else:
                diceNumber = 1

            #compute dice values
            tmp = 0
            for x in range( diceNumber ):
                tmp += diceRoll( value )

        else:
            #trickery to not change what is below
            tmp = value
            diceNumber=value
            value=1


        #perform add/substract operation
        logMsg="parseAndRollDice: Performed a series of roll for '{}' which resulted in "
        logMsg.format( match.group() )
        if match.group("operation") == "-": #if "operation" didn't produce a match, default to 'add'
            res -= tmp
            minVal -= diceNumber*value
            maxVal -= diceNumber
            logMsg+="res-={}, minVal-={}, maxVal-={}.".format( tmp, (diceNumber*value), diceNumber )
        else:
            res += tmp
            minVal += diceNumber
            maxVal += diceNumber*value
            logMsg+="res+={}, minVal+={}, maxVal+={}.".format( tmp, diceNumber, (diceNumber*value) )

        #logMsg
        loc_log.debug( logMsg )

    return res,minVal,maxVal



def compareThresh(value,threshold,mode,inclusive, *, default=False):
    """Returns a boolean only if value satisfies the threshold test. In case of failure of any sort, returns the default value (which defaults to 'False').
    
    Accepted mode values are '<', '>', '<=' and '>='."""
    
    #normalizing input
    if inclusive:
        if mode == ">":
            mode = ">="
        elif mode == "<":
            mode = "<="

    if mode == "<": return value < threshold
    elif mode == ">": return value > threshold
    elif mode == "<=": return value <= threshold
    elif mode == ">=": return value >= threshold

    return default




def thresholdRoll(expression,threshold,mode, *, inclusive=False):
    """Performs rolls according to 'expression' and tests if the resulting value passes the threshold test. Returns a tuple (success,value)."""

    val,minVal,maxVal = parseAndRollDice(expression)
    success = compareThresh(val,threshold,mode,inclusive)
    return success,val




def successRoll(expression,threshold,mode, *, inclusive=False):
    """Counts how many rolls are below/above threshold value, and returns a tuple of (successCount,tries) .

    All dice expression should be of the "+" kind. If any "-" expression or constant is present, returns None.
    If mode is not '<<' or '>>', returns None."""


    #mode check
    if mode == "<<": mode = "<"
    elif mode == ">>": mode = ">"
    else:
        loc_log.debug("successRoll: Invalid mode '{}', returning None.".format(mode))
        return None

    #init
    count=0
    tries=0

    #main loop
    for match in diceParser.finditer(expression):

        #check if valid expression for counting
        if not match.group("isDice") or match.group("operation") == "-":
            loc_log.debug("successRoll: Invalid dice expression '{}', returning None.".format(match.group()) )
            return None

        #retrieve relevant dice info
        value = int( match.group("value") )
        tmp = match.group("diceNumber")
        if tmp:
            diceNumber = int( tmp )
        else:
            diceNumber = 1

        #roll dice
        for x in range( diceNumber ):
            tmp = diceRoll( value )
            if compareThresh( tmp, threshold, mode, inclusive):
                count += 1

        tries+=diceNumber


        #perform logging
        logMsg="successRoll: Performed a series of roll for '{}', current status is "
        logMsg.format( match.group() )
        logMsg+="count={}, tries={}.".format( count, tries )
        loc_log.debug( logMsg )

    return count, tries




def diceExpressionRoll(expression):
    """Filters out invalid expression, and delegate to the appropriate rolling function depending on detected mode.
    See those functions for possible return Values. Should always returns 'None' in case of failure."""


    loc_log.debug("diceExpressionRoll: Invoked with argument '{}'.".format(expression) )

    m=diceExp.fullmatch(expression)
    if not m:
        loc_log.debug("diceExpressionRoll: Invalid expression, returning None.")
        return None


    mod = m.group("modifier")
    if mod:
        inclusive = True if m.group("inclusive") else False     #force conversion to bool
        threshold = float(m.group("modValue"))

        if len(mod) == 2:   #counting mode
            loc_log.debug("diceExpressionRoll: Delegating to successRoll.")
            return successRoll( m.group("diceExp"), threshold, mod, inclusive=inclusive)

        if len(mod) == 1:   #threshold mode
            loc_log.debug("diceExpressionRoll: Delegating to thresholdRoll.")
            return thresholdRoll( m.group("diceExp"), threshold, mod, inclusive=inclusive)

    else:                   #default mode
        loc_log.debug("diceExpressionRoll: Delegating to parseAndRollDice (default mode).")
        return parseAndRollDice( m.group("diceExp") )



def _internalInlineRollChecker(inline_expression):
    """Function to extract the appropriate dice expression (modifier included) from an inline string"""
    m=inlineTester.search(inline_expression)  #returns FIRST match
    if m :
        loc_log.debug("_inernalInlineRollChecker: Received an inline roll\n")
        return diceExpressionRoll( m.group() )
    else:
        return None



def makeRollAnswerStr( roll_res, mention_str ):
    """Formats an answer string depending on the roll result. If provided with an invalid roll result, returns 'None'."""

    answer = None

    if roll_res == None:
        answer = "Invalid dice expression !"

    elif len(roll_res)==2:  #either threshold or success roll
        res,aux = roll_res

        if isinstance(res,bool):    #threshold roll
            #care, bool apparently extand from int in python
            if res:
                answer = "{} succeeded ! (Roll value was: `{}`)".format(mention_str,aux)
            else:
                answer = "{} failed ! (Roll value was: `{}`)".format(mention_str,aux)

        elif isinstance(res,int):   #success roll
            answer = "{} succeeded `{}` times ! (Number of attempts: `{}`)".format(mention_str,res,aux)


    elif len(roll_res)==3:  #default roll
        res,minVal,maxVal = roll_res
        answer = "{} rolled a `{}`! (Possible values between `{}` and `{}`)".format(mention_str,res,minVal,maxVal)

    if answer == None:
        loc_log.warning("makeRollAnswerStr: The 'roll_res' argument '{}' is invalid !".format(roll_res))

    return answer



class RPGCommands:
    """A cog to process RPG commands and utilities."""

    #CD_Manager=CooldownManager()
    #cooldown=60
    #timeout=10

    def __init__(self,bot):
        self.bot=bot
        self.allowInlineRolls=True  #need to make it per/server
        return



    @commands.command(pass_context=True, aliases=["ir"], no_pm=True)
    @asyncio.coroutine
    def inlineRolls(self, ctx, *args):
        loc_log.info("RPGCommands.inlineRolls: Command invoked.")
        if self.allowInlineRolls:
            loc_log.debug("RPGCommands.inlineRolls: Disabling inline rolls.\n")
            msg="Inline rolls are now disabled."
        else:
            loc_log.debug("RPGCommands.inlineRolls: Enabling inline rolls.\n")
            msg="Inline rolls are now enabled."

        self.allowInlineRolls = not self.allowInlineRolls

        yield from self.bot.say( msg )
        loc_log.info("RPGCommands.inlineRolls: Command complete\n")
        return



    @commands.command(pass_context=True, aliases=["r"], no_pm=True)
    @asyncio.coroutine
    def roll(self, ctx, *args):
        loc_log.info("RPGCommands.roll: Command invoked")
        expression=" ".join(args)
        tmp = diceExpressionRoll(expression)
        answer = makeRollAnswerStr( tmp, ctx.message.author.mention )
        if answer == None:
            loc_log.critical("RPGCommands.roll: Something went very wrong in the roll procedure!\n")
            return
        yield from self.bot.say( answer )
        loc_log.info("RPGCommands.roll: Command complete\n")
        return



    @asyncio.coroutine
    def on_message(self,message):
        if self.allowInlineRolls and not message.author.bot and message.content[:2] != "./" :
            tmp = _internalInlineRollChecker( message.content )
            if tmp == None: return  #not a valid inline roll expression, or erroneous -> ignore
            answer = makeRollAnswerStr( tmp, message.author.mention )
            if answer == None:
                loc_log.critical("RPGCommands.on_message::inline_roll hook: Something went very wrong in the roll procedure!\n")
                return
            yield from self.bot.send_message( message.channel, content=answer )
        return





def main(token):
    description="Slyfer11's bot"
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('./'), description=description)

    bot.add_cog(RPGCommands(bot))

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
    handler = logging.FileHandler(filename='log/rpg.log', encoding='utf-8', mode='w')
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
