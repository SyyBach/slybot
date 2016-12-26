#!/usr/bin/python3

import discord
from discord.ext import commands
import asyncio
#from concurrent.futures import CancelledError

#from json import load as jsonloadfile
#from gc import collect as gc_collect
#from os import makedirs
#from os.path import exists as path_exists, dirname

from random import uniform, shuffle, randint #, randrange
from math import floor

from subprocess import call as sp_call, STDOUT, PIPE, DEVNULL

from os.path import join as path_join, isfile

import logging
loc_log = logging.getLogger('main.my_maths')

import re
float_detector = re.compile("[+-]?([0-9]*\.)?[0-9]+",re.I)
byte_detector = re.compile('(?:[01]?[0-9]?[0-9])|(?:2[0-4][0-9])|(?:25[0-5])',re.I)



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



def integer_round_to_precision( number, precision ):
    return floor( number * (10**precision) +.5 )

def float_round_to_precision( number, precision ):
    return float( integer_round_to_precision(number,precision) )/(10**precision)

def truncate_to_precision( number, precision ):
    return float( int(number * (10**precision)) )/(10**precision)


def call_latex( formula_str, jobname='tmplatex', outdir='data/latex/', *, return_name=False):
    cmd = [ 'pdflatex' ]
    flags = ['-interaction=nonstopmode', '-halt-on-error', '-jobname', jobname, '-output-directory', outdir ]
    arg = r'"\def\formula{' + formula_str + r'}\input{data/latex/formula.tex}"'

    cmd = cmd + flags + [ arg ]

    #print("call_latex: Will provide the following list to sp_call '{}'.".format(cmd))
    loc_log.debug("call_latex: Will provide the following list to sp_call '{}'.".format(cmd))

    rcode = sp_call(cmd, stdout=DEVNULL, stderr=STDOUT) #discards stdout/stderr, need to switch to popen?

    if return_name:
        return rcode, outdir, jobname
    else:
        return rcode


def call_latex_tikz( formula_str, jobname='tmplatex', outdir='data/latex/', *, return_name=False):
    cmd = [ 'pdflatex' ]
    flags = ['-interaction=nonstopmode', '-halt-on-error', '-jobname', jobname, '-output-directory', outdir ]
    arg = r'"\def\formula{' + formula_str + r'}\input{data/latex/tikz.tex}"'

    cmd = cmd + flags + [ arg ]

    #print("call_latex: Will provide the following list to sp_call '{}'.".format(cmd))
    loc_log.debug("call_latex_tikz: Will provide the following list to sp_call '{}'.".format(cmd))

    rcode = sp_call(cmd, stdout=DEVNULL, stderr=STDOUT) #discards stdout/stderr, need to switch to popen?

    if return_name:
        return rcode, outdir, jobname
    else:
        return rcode


def call_convert( inname='tmplatex.pdf', indir='data/latex/', outname = "tmplatex.png", outdir = "data/latex/", *, return_name=False):
    #infile=indir+inname
    infile = path_join(indir, inname)
    #outfile=outdir+outname
    outfile = path_join(outdir, outname)

    cmd = [ 'convert' ]
    inflags = [ '-density', '300' ]
    outflags = [ '-quality', '90' ]
    cmd += inflags + [ infile ] + outflags + [ outfile ]

    #print("call_convert: Will provide the following list to sp_call '{}'.".format(cmd))
    loc_log.debug("call_convert: Will provide the following list to sp_call '{}'.".format(cmd))

    rcode = sp_call(cmd, stdout=DEVNULL, stderr=STDOUT) #discards stdout/stderr, need to switch to popen?

    if return_name:
        return rcode, outfile
    else:
        return rcode


class LatexFormula:

    preserved_count = -1
    preserved_dir = 'data/latex/preserve/'
    build_dir = 'data/latex/build/'


    def __init__(self,bot,channel,formula_str,author, *, preserve=False, name=None, tikz=False):
        self.bot=bot
        self.channel=channel
        self.formula_str=formula_str
        self.author=author
        self.tikz=tikz
        self.completion= asyncio.Event()

        if LatexFormula.preserved_count == -1:
            from os import listdir
            LatexFormula.preserved_count = len( listdir(LatexFormula.preserved_dir) )   #lazy way

        if name != None :
            if isfile(path_join(LatexFormula.preserved_dir, name+'.png')):
                self.name = 'duplicate_{:02}'.format(LatexFormula.preserved_count)
                LatexFormula.preserved_count += 1   #no asyncio stuff, so no lock required here
            else:
                self.name=name
        elif preserve:
            self.name = 'preserved_{:02}'.format(LatexFormula.preserved_count)
            LatexFormula.preserved_count += 1   #no asyncio stuff, so no lock required here
        else:
            self.name=None
        
        self.task=asyncio.async(self.start())



    @asyncio.coroutine
    def start(self):
        rcode,dirname,jobname = self.call_latex()
        if rcode != 0:
            loc_log.warning("LatexFormula.start: return code for pdflatex subprocess non 0, rcode = '{}'.".format(rcode))
            msg="{} Could not process the latex formula !".format(self.author.mention)
            yield from self.bot.send_message(self.channel, content=msg)
            self.completion.set()
            return
        rcode,filename = self.call_convert(jobname = jobname, indir = dirname)
        if rcode != 0:
            loc_log.warning("LatexFormula.start: return code for convert subprocess non 0, rcode = '{}'.".format(rcode))
            msg="{} Could not convert to png !".format(self.author.mention)
            yield from self.bot.send_message(self.channel, content=msg)
            self.completion.set()
            return
        loc_log.info("LatexFormula.start: All subprocesses completed normally.")
        yield from self.send_embed_pic(filename)
        self.completion.set()
        return


    def call_latex(self):
        """Encapsulate the global call_latex function for LatexFormula use cases."""
        if self.tikz:
            latex_function = call_latex_tikz
        else:
            latex_function = call_latex

        if self.name:
            return latex_function( self.formula_str, self.name, LatexFormula.build_dir[:-1], return_name=True )
        else:
            return latex_function( self.formula_str, outdir=LatexFormula.build_dir[:-1], return_name=True )
#        if self.name:
#            return call_latex( self.formula_str, self.name, LatexFormula.build_dir[:-1], return_name=True, tikz=self.tikz)
#        else:
#            return call_latex( self.formula_str, outdir=LatexFormula.build_dir[:-1], return_name=True, tikz=self.tikz)


    def call_latex_tikz(self):
        """Encapsulate the global call_latex function for LatexFormula use cases."""
        if self.name:
            return call_latex_tikz( self.formula_str, self.name, LatexFormula.build_dir[:-1], return_name=True)
        else:
            return call_latex_tikz( self.formula_str, outdir=LatexFormula.build_dir[:-1], return_name=True )

    def call_convert(self, jobname, indir):
        """Encapsulate the global call_convert function for LatexFormula use cases."""
        if self.name:
            return call_convert( jobname+'.pdf', indir, jobname+'.png', LatexFormula.preserved_dir, return_name=True)
        else:
            return call_convert( jobname+'.pdf', indir, jobname+'.png', return_name=True)



    @asyncio.coroutine
    def send_embed_pic(self,filename):
        fp=open(filename,'rb')
        yield from self.bot.send_file(self.channel, fp, filename=filename, content=self.author.mention)
        fp.close()
        return



class Pytha:

    opening = """:question: Consider a triangle ABC that has a right angle at vertex C.\n"""

    def __init__(self, manager,server,channel,member, tries=2):
        self.bot=manager.bot
        self.server=server
        self.channel=channel
        self.member=member

        self.manager=manager
        self.dieNotif_sent=False
        self.key = (self.channel,self.member)

        self.timeout = 5.*60
        self.guessed=asyncio.Event()
        self.stop=False
        if tries < 1:
            self.tries = 2
        else:
            self.tries=tries

        #shuffling and randomness
        self.seg = ["a", "b", "c"]
        shuffle( self.seg )
        self.length = { self.seg[i] : randint(1,50) for i in range(2) }

        #computing answer and inverting stuff
        if self.seg[2] == "c":
            self.length[ self.seg[2] ] = Pytha.computeHypo( self.length[ self.seg[0] ], self.length[ self.seg[1] ] )
        elif self.seg[1] == "c":
            if self.length[self.seg[0]] > self.length["c"]:
                tmp = self.length["c"]
                self.length["c"] = self.length[ self.seg[0] ]
                self.length[ self.seg[0] ] = tmp
            self.length[ self.seg[2] ] = Pytha.computeSide( self.length[ self.seg[0] ], self.length[ self.seg[1] ] )
        else:
            if self.length[self.seg[1]] > self.length["c"]:
                tmp = self.length["c"]
                self.length["c"] = self.length[ self.seg[1] ]
                self.length[ self.seg[1] ] = tmp
            self.length[ self.seg[2] ] = Pytha.computeSide( self.length[ self.seg[1] ], self.length[ self.seg[0] ] )
        
        #making problem string
        self.problem_str=self.member.mention + " "
        self.problem_str+=Pytha.opening+"Assuming that we have:\n`{} = {}`\n".format(self.seg[0],self.length[self.seg[0]])
        self.problem_str+="`{} = {}`\nwhat is the length of side `{}`?".format(self.seg[1],self.length[self.seg[1]],self.seg[2])

        self.task=asyncio.async(self.start())
        return



    @asyncio.coroutine
    def start(self):
        loc_log.info("Pytha.start: Invoked.")

        #Opening message
        msg=self.problem_str+"\n(Problem will be cancelled after {} minutes of inactivity.)".format(self.timeout/60.)
        yield from self.bot.send_message(self.channel, content=msg )

        #wait for answers
        while(not self.stop and self.tries>0):
            msg = yield from self.bot.wait_for_message(self.timeout,author=self.member,channel=self.channel)

            if msg == None:     #timeout occured
                loc_log.warning("Pytha.start: Timeout, cancelling.")
                msg = "{} Timed out, cancelling.".format(self.member.mention)
                msg += " The answer was `{}`. Better luck next time.".format(self.length[self.seg[2]])
                yield from self.bot.send_message(self.channel, content=msg )
                break

            yield from self.process_answer_str( msg.content )
        

        self.internal_die_notice()

        loc_log.info("Pytha.start: Procedure over.\n")
        return



    def internal_die_notice(self):
        if self.dieNotif_sent:
            loc_log.debug("Pytha.internal_die_notice: A 'die' notification has already been sent, ignoring.")
            return
        loc_log.debug("Pytha.internal_die_notice: Sending 'die' notification to free current channel/member.")
        asyncio.async( self.manager.internal_die_management(self, key=self.key) )
        self.dieNotif_sent=True
        return

        

    def is_good_answer(self, answer, precision=1):
        answer = integer_round_to_precision( answer, precision )
        return answer == integer_round_to_precision( self.length[self.seg[2]], precision )



    @asyncio.coroutine
    def process_answer_str(self, answer_str, precision=1):
        loc_log.info("Pytha.process_answer_str: Invoked with argument '{}'.".format(answer_str) )
        match = float_detector.search( answer_str )
        if not match:
            loc_log.info("Pytha.process_answer_str: no float detected.")
            return

        answer = float( match.group() )
        self.tries -= 1

        if self.is_good_answer( answer, precision ):
            self.guessed.set()
            self.stop=True
            msg = "Well done {}, you found the answer `{}` !".format(self.member.mention,self.getDisplayFloat(1))
        else:
            msg = "{} Nope, `{}` is not the answer (required precision: `{}` decimal digit(s)).".format(self.member.mention,answer,precision)
            msg += " You have `{}` attempt(s) left.".format(self.tries)
            if self.tries == 0:
                msg += " The answer was `{}` (rounded from `{}...`). Better luck next time.".format(self.getDisplayFloat(1),self.getTruncFloat(4))

        yield from self.bot.send_message( self.channel, content=msg )

        return



    def getDisplayFloat(self, precision):
        return float_round_to_precision( self.length[self.seg[2]], precision )



    def getTruncFloat(self, precision):
        return truncate_to_precision( self.length[self.seg[2]], precision )



    @staticmethod
    def computeHypo( side_a, side_b ):
        return ( side_a*side_a + side_b*side_b )**.5


    @staticmethod
    def computeSide( side, hypo):
        return ( hypo*hypo - side*side )**.5


    @staticmethod
    def make_key( ctx ):
        key = ( ctx.message.channel, ctx.message.author )
        return key


    @staticmethod
    def key_exists( key, manager ):
        channel, member = key
        name_str = member.nick if member.nick else member.name
        if key in manager.resDict:
            return True,"A Pythagoras problem is already running in this chanel for {}".format(name_str)

        else:
            return False,"No Pythagoras problem is running in this channel for {}".format(name_str)



class ResourceManager:
    def __init__(self,bot):
        self.bot=bot
        self.lock=asyncio.Lock()    #"semaphore" for resDict. It is NOT thread safe, only coroutine safe !!!
        self.resDict= {}           #dictionary of reserved resources. key: stuff, item: the guy who made the reservation
        loc_log.info("ResourceManager initialized.")


    @asyncio.coroutine
    def resDict_safeAdd(self,key,value, timeout=10, feedback_channel=None):
        try:
            yield from asyncio.wait_for( self.lock.acquire(), timeout )
        except asyncio.TimeoutError:
            loc_log.exception("ResourceManager.resDict_safeAdd: Could not acquire gameDict lock, returning False.")
            if feedback_channel:
                errMsg="ResourceManager: Could not acquire resDict lock (add operation), someone else probably crashed?"
                yield from self.bot.send_message(feedback_channel, content=errMsg)

            return False

        self.resDict[key]=value
        self.lock.release()
        return True


    @asyncio.coroutine
    def resDict_safePop(self,key,timeout=10,feedback_channel=None):
        try:
            yield from asyncio.wait_for( self.lock.acquire(), timeout )
        except asyncio.TimeoutError:
            loc_log.exception("ResourceManager.resDict_safePop: Could not acquire resDict lock, returning None.")
            if feedback_channel:
                errMsg="ResourceManager: Could not acquire resDict lock (pop operation), someone else probably crashed?"
                yield from self.bot.send_message(feedback_channel, content=errMsg)
            return None

        ret=self.resDict.pop(key)
        self.lock.release()
        return ret


    @asyncio.coroutine
    def internal_die_management(self, obj, key=None):
        #the resource may not be in resDict if it was created but failed to register because of lock issues
        loc_log.info("ResourseManager.internal_die_management: Received a die notice from '{}'.".format(obj))

        if key == None:
            key = obj.channel

        if key in self.resDict:
            tmp=yield from self.resDict_safePop( key )
            if tmp != obj:
                msg="ResourceManager: popped item doesn't match input obj argument, expect more errors!"
                yield from self.bot.send_message( obj.channel, content=msg)
                yield from self.bot.send_message( tmp.channel, content=msg)
                loc_log.critical("ResourceManager.internal_die_management: Popped item and argument don't match!\n")
            else:
                loc_log.info("ResourceManager.internal_die_management: 'die' notice management completed normally.\n")
        else:
            loc_log.critical("ResourceManager.internal_die_management: Couldn't find any resource item with the key '{}'!\n".format(key) )
        
        return






class MathsCog:
    """A cog to process Maths stuff."""


    def __init__(self,bot):
        self.bot=bot
        self.rManager = ResourceManager(self.bot)
        return


    
    @commands.command(pass_context=True, aliases=["p"], no_pm=True)
    @asyncio.coroutine
    def pythagoras(self, ctx, *args):
        loc_log.info("MathsCog.pythagoras: Command invoked.")
        
        key = Pytha.make_key(ctx)
        key_exists,msg = Pytha.key_exists( key, self.rManager )
        if key_exists:
            yield from self.bot.say( "MathsCog: "+msg )
            loc_log.warning("MathsCog.pythagoras: Resource in use, cancelling. key: '{}'.\n".format(key))
            return

        obj = Pytha(self.rManager, ctx.message.server, ctx.message.channel, ctx.message.author)
        yield from self.rManager.resDict_safeAdd(key,obj)
        loc_log.info("MathsCog.pythagoras: Completed.\n")
        return



    @commands.command(pass_context=True, aliases=["pq"], no_pm=True)
    @asyncio.coroutine
    def pythagorasQuit(self, ctx, *args):
        loc_log.info("MathsCog.pythagorasQuit: Command invoked.")

        key = Pytha.make_key(ctx)
        key_exists,msg = Pytha.key_exists( key, self.rManager )
        if not key_exists:
            yield from self.bot.say( "MathsCog: "+msg )
            loc_log.warning("MathsCog.pythagoras: Resource not used, cancelling. key: '{}'.\n".format(key))
            return

        yield from self.bot.say("MathsCog: Cancel request for Pythagoras problem received.")

        obj = yield from self.rManager.resDict_safePop( key )
        if obj == None:
            yield from self.bot.say("MathsCog: Error, retrieved item is invalid.")
            loc_log.critical("MathsCog.pythagoras: Received 'None' for key: '{}', cancelling.\n".format(key))
            return
        obj.stop=True
        obj.tries=-1
        obj.task.cancel()

        yield from asyncio.sleep(5)
        if obj.task.cancelled():
            self.bot.say("MathsCog: Pythagoras problem cancelled.")
            loc_log.info("MathsCog.pythagorasQuit: Completed timely.\n")
        else:
            yield from asyncio.sleep(obj.timeout)
            if not obj.task.cancelled():
                loc_log.critical("MathsCog.pythagorasQuit: Task was not cancelled ! key: '{}'.\n".format(key) )
            else:
                loc_log.info("MathsCog.pythagorasQuit: Completed by timeout?\n")
        return



    @commands.command(pass_context=True, aliases=["tex"], no_pm=True)
    @asyncio.coroutine
    def latex(self, ctx, *args):
        if len(args) == 0 or "-h" in args:
            yield from self.bot.say("MathsCog.latex: `./latex <latex formula>`\nProcesses the <latex formula> into a png image and send it to the chat.")
            return

        key = "LatexFormula"
        if key in self.rManager.resDict:
            yield from self.bot.say('MathsCog: Already busy processing another formula.')
        else:
            add_success = yield from self.rManager.resDict_safeAdd(key,None) #restrict usage of command
            if not add_success:
                yield from self.bot.say('MathsCog: Could not reserve Formula processing resource !')
                loc_log.warning("MathsCog.latex: Error while reserving the 'LatexFormula' resource.\n")
            else:
                loc_log.info("MathsCog.latex: 'LatexFormula' resource reserved, processing will start.")
                formula_str=' '.join(args)
                latex_formula = LatexFormula(self.bot,ctx.message.channel,formula_str,ctx.message.author)
                self.rManager.resDict[key] = latex_formula  #store in the actual object using the resource
                task = asyncio.async(latex_formula.completion.wait())
                try:
                    yield from asyncio.wait_for( task, timeout=60 )
                    yield from self.rManager.resDict_safePop(key)
                    loc_log.info("MathsCog.latex: Process completed.\n")
                except asyncio.TimeoutError:
                    loc_log.critical("MathsCog.latex: Could not complete after timeout, resource 'LatexFormula' will remain locked !\n")
                    self.bot.say("MathsCog: Something very wrong happened, 'latex' command will be disabled.")
        return



    @commands.command(pass_context=True, aliases=["pgf"], no_pm=True)
    @asyncio.coroutine
    def tikz(self, ctx, *args):
        if len(args) == 0 or "-h" in args:
            yield from self.bot.say("MathsCog.tikz: `./tikz <formula>`\nProcesses the <formula> as tikz instructions into a png image and send it to the chat.")
            return

        key = "LatexFormula"
        if key in self.rManager.resDict:
            yield from self.bot.say('MathsCog: Already busy processing another formula.')
        else:
            add_success = yield from self.rManager.resDict_safeAdd(key,None) #restrict usage of command
            if not add_success:
                yield from self.bot.say('MathsCog: Could not reserve Formula processing resource !')
                loc_log.warning("MathsCog.tikz: Error while reserving the 'LatexFormula' resource.\n")
            else:
                loc_log.info("MathsCog.tikz: 'LatexFormula' resource reserved, processing will start.")
                formula_str=' '.join(args)
                latex_formula = LatexFormula(self.bot,ctx.message.channel,formula_str,ctx.message.author, tikz=True)
                self.rManager.resDict[key] = latex_formula  #store in the actual object using the resource
                task = asyncio.async(latex_formula.completion.wait())
                try:
                    yield from asyncio.wait_for( task, timeout=60 )
                    yield from self.rManager.resDict_safePop(key)
                    loc_log.info("MathsCog.tikz: Process completed.\n")
                except asyncio.TimeoutError:
                    loc_log.critical("MathsCog.tikz: Could not complete after timeout, resource 'LatexFormula' will remain locked !\n")
                    self.bot.say("MathsCog: Something very wrong happened, 'latex' related commands will be disabled.")
        return


    @asyncio.coroutine
    def on_message(self,message):
        pass



    #temporary fix
    @commands.command(pass_context=True, no_pm=True)
    @asyncio.coroutine
    def rgb(self, ctx, *args):
        if len(args) < 4 or "-h" in args:
            yield from self.bot.say("MathsCog: `./rgb <R> <G> <B> <text>`\nProcesses the <text> through latex using the RGB code provided into a png image and send it to the chat.")
            return

        red = byte_detector.fullmatch( args[0] )
        green = byte_detector.fullmatch( args[1] )
        blue = byte_detector.fullmatch( args[2] )
        if not red or not green or not blue:
        #if red<0 or red>255 or green<0 or green>255 or blue<0 or blue>255:
            yield from self.bot.say('MathsCog: Invalid RGB code, use integers between 0 and 255.')
            return

        red = int(red.group())
        green = int(green.group())
        blue = int(blue.group())
        
        color = '{},{},{}'.format(red,green,blue)
        color = r'\definecolor{tmpcolor}{RGB}{' +color+ r'}'

        formula_str = ' '.join(args[3:])
        formula_str = color + r'\text{\color{tmpcolor}' + formula_str + r'}'
        
        yield from self.latex_abstraction(ctx.message.channel,ctx.message.author,formula_str)
        return



    @commands.command(pass_context=True, aliases=["newcolor","newColor"], no_pm=True)
    @asyncio.coroutine
    def newRGBColor(self, ctx, *args):
        if len(args)!=4 or "-h" in args:
            yield from self.bot.say("MathCog: `./newRGBColor <name> <R> <G> <B>`\n Register the provided RGB code under <name>, to be used with the `./color` command.")
            return

        red=byte_detector.fullmatch( args[1] )
        green=byte_detector.fullmatch( args[2] )
        blue=byte_detector.fullmatch( args[3] )
        if not red or not green or not blue:
            yield from self.bot.say('MathsCog: Invalid RGB code, use integers between 0 and 255.')
            return

        name=args[0]
        return




    @asyncio.coroutine
    def latex_abstraction(self,channel,author,formula_str, *, tikz=False):
        key = "LatexFormula"
        if key in self.rManager.resDict:
            yield from self.bot.send_message(channel, content='MathsCog: Already busy processing another formula.')
        else:
            add_success = yield from self.rManager.resDict_safeAdd(key,None) #restrict usage of command
            if not add_success:
                yield from self.bot.send_message(channel, content='MathsCog: Could not reserve Formula processing resource !')
                loc_log.warning("MathsCog.latex: Error while reserving the 'LatexFormula' resource.\n")
            else:
                loc_log.info("MathsCog.latex: 'LatexFormula' resource reserved, processing will start.")
                #formula_str=' '.join(args)
                latex_formula = LatexFormula(self.bot,channel,formula_str,author, tikz=tikz)
                self.rManager.resDict[key] = latex_formula  #store in the actual object using the resource
                task = asyncio.async(latex_formula.completion.wait())
                try:
                    yield from asyncio.wait_for( task, timeout=60 )
                    yield from self.rManager.resDict_safePop(key)
                    loc_log.info("MathsCog.latex: Process completed.\n")
                except asyncio.TimeoutError:
                    loc_log.critical("MathsCog.latex: Could not complete after timeout, resource 'LatexFormula' will remain locked !\n")
                    self.bot.send_message(channel, content="MathsCog: Something very wrong happened, 'latex' command will be disabled.")
        return



def main(token):
    description="Slyfer11's bot"
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('./'), description=description)

    bot.add_cog(MathsCog(bot))

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
    logger = logging.getLogger('my_maths')
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(filename='log/my_maths.log', encoding='utf-8', mode='w')
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
