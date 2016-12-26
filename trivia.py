#!/usr/bin/python3

import discord
from discord.ext import commands
import asyncio
from concurrent.futures import CancelledError

#from json import load as jsonloadfile
from json import loads as jsonloadstr
from gc import collect as gc_collect
from os import makedirs
from os.path import exists as path_exists, dirname

from random import randrange
#from math import exp

from str_util import *

import logging
loc_log = logging.getLogger('main.trivia')
#logger.setLevel(logging.INFO)
#handler = logging.FileHandler(filename='log/trivia.log', encoding='utf-8', mode='w')
#handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
#logger.addHandler(handler)






class QC_Manager:
    """Manager to ensure we have singleton-like QCategory."""

    #the class definition ensure "privacy" of the _instances member
    _instances = set()  #the set that will keep track of the instances we already created
    simple_eq = True   #flag to force simpler and faster string comparison/creation of QCategory


    def __call__(self,inStr):
        if inStr == None:
            inStr="NoCategory"

        #ensure singleton behaviour
        for instance in self._instances:     #loop on existing instances
            if instance == inStr:           #check if inStr corresponds to an instance
                #match found, update aliases with display_str and return instance
                instance.add_alias(inStr)
                return instance

        #no match found, need new instance
        instance = QCategory( inStr )
        #and add the created instance to the static set
        self._instances.add( instance )
        return instance



    def _destroy(self,qcat):
        """Should not play with this guy. Utility to remove QCategory from the registered set of _instances.
        Returns True only on successful removal. Returns False otherwise and should not raise Exception."""

        if not isinstance(qcat,QCategory):
            loc_log.warning("QC_Manager._destroy: The provided argument '{}' is not a QCategory, ignoring.".format(qcat))
            return False

        try:
            QC_Manager._instances.remove(qcat)
        except KeyError:
            loc_log.exception("QC_Manager._destroy: The specified QCategory '{}' is not registered! Ignoring.".format(qcat))
            return False

        return True


qc_manager=QC_Manager()


#TODO: check if collections.UserString is any good for this stuff
#TODO: merge operation for QCategory that pass __eq__ but different aliases?
class QCategory:
    """Represents a hopefully smart Question Category"""

    def __init__(self,inStr):
        self.display_string = QCategory.make_display_name(inStr)
        self.id = hash( clean_str(self.display_string,DL_dist=True) )   #should be defined to ensure hash makes sense
        self.alias = { self.display_string }
        return


    def __eq__(self,other):
        if isinstance(other,str):
            work_str=other
        elif isinstance(other,QCategory):
            work_str=other.display_string
        else:
            return NotImplemented

        if QC_Manager.simple_eq:
            return clean_str( self.display_string, DL_dist=True ) == clean_str( work_str, DL_dist=True )
        else:
            return similar_string_test(self.display_string,work_str)


    def __hash__(self):
        return self.id


    def __str__(self):
        return self.display_string


    @staticmethod
    def make_display_name(inStr):
        return clean_str(inStr, lowercase=False, remove_symbols=False, remove_special=True)


    def add_alias(self,inStr):
        self.alias.add( QCategory.make_display_name(inStr) )
        return


    def _absorb(self,other):
        """Utility to absorb another QCategory. Absorb and not merge."""
        #Preserves self.display_string and self.id, update aliases and destroy other
        self.alias = self.alias + other.alias
        if not other._unregister():
            loc_log.error("QCategory._absorb: Could not unregister '{}' from QC_Manager!".format(other))
        return


    def _unregister(self):
        """Utility to unregister from QC_Manager. Dumb stuff, but helps to keep the logic local?
        Returns True iff the un-registration was successful."""
        return QC_Manager._destroy(self)




class Question:
    """This class represents a question, and should provide any utility to access Question/Answer/Category."""

    def __init__(self,inDict,identifier):
        """May raise TypeError or KeyError."""

        if not isinstance(inDict, dict):
            raise TypeError('Question.__init__: input argument is not a dictionary')

        try:
            self.questionStr=inDict['Question']
            self.answerStr=inDict['Answer']
        except KeyError:
            loc_log.exception('Question.__init__: Dictionary argument does not contain minimum required keys!')
            #loc_log.debug('|| object trace:\n{}'.format(inDict))
            raise
        if not isinstance(self.questionStr, str ) or not isinstance(self.answerStr, str ):
            raise TypeError('Question.__init__: "Question" or "Answer" objects do not have Str type')

        if 'Category' in inDict:
            tmp=inDict['Category']
            if not isinstance(tmp, str ):
                raise TypeError('Question.__init__: "Category" object does not have str type')
            self.category=qc_manager(tmp)
        else:
            self.category=qc_manager(None)

        self.id = identifier
        self.hintStr = self.make_hint()


    def __lt__(self,other):
        return self.id < other.id


    def is_good_guess(self,guess):
        return similar_string_test(self.answerStr,guess)


    def make_hint(self):
        count=0
        res=list( self.answerStr )
        for idx,c in enumerate(res):
            if c == " ":
                res[ idx ] = "  "   #double spaces for clarity
                continue

            count += 1
            if count <= len(self.answerStr) / 5:
                continue
            if count % 3 == 0:
                continue
            
            res[ idx ] = "."
        return " ".join(res)



class QuestionPool:
    """Represents the pool of available Question's"""

    ## static members
    initialized=False
    categoryPools={}   #dictionary of sets
    category_list_string=""
    questionCount=0
    defaultPool="data/questions.json"   #this guy is immutable so no worries if it is public
    defaultCustomPool="data/customQuestions.json"


    def __init__(self,filepath=None):

        if QuestionPool.initialized:
            loc_log.info("QuestionPool.__init__: QuestionPool.categoryPools is already initialized.")
        else:
            self.init(filepath)     #load questions


        self.old_questions = { k:set() for k in QuestionPool.categoryPools.keys() } 
        self.pull_count = 0
        self.pool_exhausted = asyncio.Event()
        return


    def init(self,filepath=None):
        if QuestionPool.initialized:
            return  #redundant

        #load default question file
        if not path_exists(QuestionPool.defaultPool):
            loc_og.error("QuestionPool.init: Core questions pool file is missing !")
        else:
            self.__load(QuestionPool.defaultPool)

        #load optional default file
        if path_exists(QuestionPool.defaultCustomPool):
            self.__load(QuestionPool.defaultCustomPool)
        else:
            makedirs( dirname(QuestionPool.defaultCustomPool) , exist_ok=True )
            open(QuestionPool.defaultCustomPool, 'a').close()

        #load optional argument file
        if filepath and path_exists(filepath):
            self.__load(filepath)
        elif filepath:
            loc_log.warning("QuestionPool.init: The provided file '{}' could not be found, skipping.".format(filepath))
        else:
            loc_log.debug("QuestionPool.init: There was no optional file for the question pool.")


        #remove extra 2 leading charcters from category_list_string
        if len(QuestionPool.category_list_string) > 2:
            QuestionPool.category_list_string = QuestionPool.category_list_string[2:]



        if QuestionPool.questionCount == 0:
            loc_log.critical("QuestionPool.init: Could not load any questions, trivia will be non functional.")

        #set "initialized" flag to True
        QuestionPool.initialized=True
        
        return


    def __load(self, filepath):
        """Internal function utility to load questions from json files. Perform a variety of checks but should catch most exceptions and only notify owner."""

        loc_log.info("QuestionPool.__load: Loading from file '{}'".format(filepath))
        self.__veryInternalLoad(filepath)
        #force a garbage collector call to forcibly free the "tmp" variable of __veryInternalLoad
        gc_collect()

        return


    def __veryInternalLoad(self, filepath):
        try:
            f=open(filepath,'r')
            tmp=f.read()
        except OSError:
            loc_log.exception("QuestionPool.__veryInternalLoad: could not read file '{}'".format(filepath))

        if not tmp:
            loc_log.info("QuesitonPool.__veryInternalLoad: file '{}' is empty, skipping.".format(filepath))
            return


        try:
            tmp=jsonloadstr( tmp )
        except:
            log_log.exception("QuestionPool.__veryInternalLoad: something went wrong, probably when trying to deserialize data from file '{}' (json.JSONDecodeError?)".format(filepath))



        errCount=0
        for l in tmp:
            try:
                l=Question(l,QuestionPool.questionCount)
            except (TypeError,KeyError) as e:
                #ignore this one error, but keep track of how many f*ck up happened
                errCount +=1
                loc_log.debug("QuestionPool__veryInternalLoad: Couldn't load question '{}', current errCount={}.".format(l,errCount))
                continue

            #from this point on, l is a valid Question object
            if l.category in QuestionPool.categoryPools:
                QuestionPool.categoryPools[l.category].add(l)
            else:
                QuestionPool.categoryPools[l.category]={ l }
                QuestionPool.category_list_string+=", `{}`".format(l.category)
                loc_log.info("QuestionPool.__veryInternalLoad: Created a new QCategory '{}', for a total of {}".format(l.category,len(QuestionPool.categoryPools)))

            #at this point, a question was added
            QuestionPool.questionCount +=1
            if QuestionPool.questionCount % 10 == 0:
                loc_log.debug("QuestionPool.__veryInternalLoad: Added {} questions, over {} categories, with {} errors".format(QuestionPool.questionCount,len(qc_manager._instances),errCount))
                

        if errCount:    #in case of f*ck up, inform owner
            loc_log.warning("QuestionPool.__veryInternalLoad: {} invalid object read attempts from file '{}', please check the data.".format(errCount,filepath))

        return


    def pull_question(self, category=None, avoid_session_duplicate=True, avoid_recent=False):
        """Pulls a question at random. If the optional category argument does not match available categories, return a random question from the complete pool"""
        #TODO: implement avoid_recent part
        #TODO: soft warn about the no category match problem

        if QuestionPool.questionCount == 0:
            loc_log.critical("QuestionPool.pull_question: attempt to pull question from empty pool.")
            raise QuestionPool.NoQuestionError()


        #rebuild pools without old questions
        if avoid_session_duplicate and not self.pool_exhausted.is_set() :
            loc_log.debug("QuestionPool.pull_question: Removing old questions to perform a pull.")
            iter_pool={}
            for k,old in self.old_questions.items():
                iter_pool[k] = QuestionPool.categoryPools[k] - old
            loc_log.debug("QuestionPool.pull_question: Removal complete.")
        else:                           #use static categoryPools as is
            loc_log.debug("QuestionPool.pull_question: Pulling from complete pool.")
            iter_pool=QuestionPool.categoryPools

        #compute question index
        if category in iter_pool:
            loc_log.debug("QuestionPool.pull_question: Pulling from category '{}'.".format(category))
            n=len(iter_pool[category])
            if n == 1:
                self.pool_exhausted.set()
            idx=randrange( n )
        else:
            loc_log.debug("QuestionPool.pull_question: Pulling without category.")
            n = QuestionPool.questionCount - self.pull_count
            if n == 1:
                self.pool_exhausted.set()
            idx=randrange( n )
            for key,l in iter_pool.items():
                if idx >= len(l) :
                    idx -= len(l)
                else:
                    category=key
                    break

        self.pull_count += 1
        ret = list(iter_pool[ category ])
        ret.sort()
        ret = ret[idx]
        self.old_questions[ category ].add( ret )
        return ret
        #return sorted( list(iter_pool[ category ]) )[ idx ]


    def clear_old_questions(self):
        loc_log.debug("Clearing history of old questions")
        for x in self.old_questions.values():
            x.clear()
        return


    def mergeCategory(self,cat1,cat2):
        pass


    class NoQuestionError(Exception):
        def __init__(self):
            Exception.__init__(self,"QuestionPool does not have any registered Question !")



class TriviaGame:
    """Class to manage pulling question and scores and stuff..."""
    
    def __init__(self,manager,server,channel,winReq=5,showHints=True,categoryStr=None):
        self.manager=manager
        #server info stuff
        self.bot=manager.bot
        self.server=server
        self.channel=channel
        #game stuff
        self.questionPool=QuestionPool()
        self.showHints=showHints
        if winReq > 0 and winReq <= 100 :
            self.winReq=winReq 
        else:
            loc_log.warning("TriviaGame.__init__: Invalid winReq argument {}, falling back to default".format(winReq))
            self.winReq=5
            asyncio.async(self.bot.send_message(self.channel, content="Warning: winReq must be between 1 and 100, falling back to default value.".format(categoryStr) ))
        self.guess_lock=asyncio.Lock()
        self.scores={}                      #dictionary of { member : score }, where score should be an int
        if categoryStr != None:
            tmp=qc_manager(categoryStr)
            if tmp in QuestionPool.categoryPools:
                self.category=tmp
                #self.categoryStr=categoryStr
            else:
                loc_log.warning("TriviaGame.__init__: Invalid category argument '{}', falling back to default.".format(categoryStr))
                self.category=None
                asyncio.async(self.bot.send_message(self.channel, content="Couldn't find the category `{}`, proceeding with all questions.".format(categoryStr) ))
        else:
            self.category=None
        self.hint_timeout=3                 #should of course be shorter than questionDuration
        self.questionDuration=20            #duration in seconds
        #self.curQuestion=None
        self.guessed=asyncio.Event()
        self.guess_timestamp=None
        self.stopGame=False
        self.allowGuesses=False
        self.dieNotif_sent=False
        
        self.task=asyncio.async(self.startGame())
        loc_log.debug("TriviaGame.__init__: Initialization complete.")
        return


    @asyncio.coroutine
    def startGame(self):
        loc_log.info("TriviaGame.startGame: Trivia now starting.")
        while(not self.stopGame):
            loc_log.debug("TriviaGame.startGame: Question pull process started.")
            #draw new question
            if self.questionPool.pool_exhausted.is_set():
                if self.category:
                    loc_log.info("The pool for '{}' is exhausted, switching to global pool".format(self.category))
                    yield from self.bot.send_message(self.channel, content="TriviaGame: the pool of questions for category `{}` is exhausted, the game will continue with questions from all categories".format(self.category) )
                    self.category=None
                    self.questionPool.pool_exhausted.clear()
                else:
                    loc_log.info("The global pool is exhausted, resetting pool.")
                    yield from self.bot.send_message(self.channel, content="TriviaGame: the pool of questions is exhausted, the game will continue with old questions" )
                    self.questionPool.clear_old_questions()
                    self.questionPool.pool_exhausted.clear()

            try:
                self.curQuestion = self.questionPool.pull_question(self.category, True, False)
            except QuestionPool.NoQuestionError:
                loc_log.exception("TriviaGame.startGame: Couldn't pull any question from '{}'.".format(self.questionPool))
                yield from self.bot.send_message(self.channel, content="TriviaGame: couldn't pull any questions")
                break   #terminate game by ending the loop

            loc_log.debug("TriviaGame.startGame: Question pull successful, entering IO phase.")
            #message it
            yield from self.bot.send_message(self.channel, content=":question: Category: `{}`\nQuestion: **{}**\n(Question ID: `{}`)".format(self.curQuestion.category,self.curQuestion.questionStr, self.curQuestion.id) )

            #prepare to receive guesses
            self.guessed.clear()
            self.allowGuesses=True

            try:
                #wait for someone to guess, or until timeout
                yield from asyncio.wait_for(self.guessed.wait(), self.hint_timeout)
            except asyncio.TimeoutError:    #no one guessed in time
                loc_log.debug("TriviaGame.startGame: Hint timeout, sending hint.")
                yield from self.bot.send_message(self.channel, content=":clock3: Hint: `{}`".format(self.curQuestion.hintStr) )
                try:    #wait for more guesses
                    yield from asyncio.wait_for(self.guessed.wait(), self.questionDuration-self.hint_timeout)
                except asyncio.TimeoutError:
                    loc_log.debug("TriviaGame.startGame: Question timeout, cleanup and preparation for next question.")
                    #no one found the answer in time
                    self.allowGuesses=False
                    yield from self.bot.send_message(self.channel, content=":exclamation: The answer was `{}` !".format(self.curQuestion.answerStr))
        
        #yield from self.bot.send_message(self.channel, content="This trivia is over !")
        yield from self.message_leaderboard(mid_game=False)

        self.internal_die_notice()

        loc_log.info("TriviaGame.startGame: Trivia game complete.\n")
        return


    @asyncio.coroutine
    def stop(self):
        loc_log.debug("TriviaGame.stop: Recieved stop request")

        self.stopGame=True  #this flag should tell self.task to terminate the next time it goes through its main loop
        #notify channel
        yield from self.bot.send_message(self.channel, content="TriviaGame: game will terminate after the next question")

        #check for stop, or force it
        try:
            yield from asyncio.wait_for(self.task, self.questionDuration+10)
        except asyncio.TimeoutError:
            self.allowGuesses=False     #make sure guesses are disabled
            loc_log.error("TriviaGame.stop: Game stop procedure timeout, forcing stop.")
            yield from self.bot.send_message(self.channel, content="Debug info - TriviaGame: Game stop procedure timeout, forcing stop")
            yield from asyncio.sleep(10)    #sleep a bit to give time to the cancel request
            if not self.task.cancelled():
                loc_log.critical("TriviaGame.stop: Forced stop failed, no die notice will be sent.\n")
                yield from self.bot.send_message(self.channel, content="Debug info - TriviaGame: Forced stop failed")
            else:
                loc_log.debug("TriviaGame.stop: Forced stop complete.\n")

            self.internal_die_notice()

        loc_log.debug("TriviaGame.stop: Game stopped normally.\n")
        return


    @asyncio.coroutine
    def process_guess(self, author, guess, timestamp):
        try:
            yield from asyncio.wait_for( self.guess_lock.acquire(), 5 )
        except asyncio.TimeoutError:
            errMsg="Debug info - TriviaGame.process_guess: Could not acquire guess_lock, someone else probably crashed?"
            yield from self.bot.send_message(self.channel, content=errMsg)
            loc_log.critical("TriviaGame.process_guess: Could not axquire quess_lock, returning False.")
            return False

        #guess_lock is acquired ! Do not forget to release it
        if not self.curQuestion:
            #something horribly wrong must have happened in bot data flow
            loc_log.critical("TriviaGame.process_guess: No question was set, returning False.")
            self.bot.send_message(self.channel,content="Debug info - TriviaGame.process_guess: no question set! Something went really wrong!")
            self.guess_lock.release()
            return False

        if not self.guessed.is_set() and self.curQuestion.is_good_guess(guess) :
            loc_log.info("TriviaGame.process_guess: Someone guessed the answer, score processing starting.")
            self.allowGuesses=False
            self.guess_timestamp=timestamp
            if not author in self.scores:
                self.scores[ author ] = 1
            else:
                self.scores[ author ] += 1

            #announce question guesser
            #name_str = author.nick if author.nick else author.name
            yield from self.bot.send_message( self.channel, content=":white_check_mark: {} found the answer: `{}`".format(author.mention,  self.curQuestion.answerStr) )

            #check for trivia winner
            if self.scores[ author ] == self.winReq:
                loc_log.info("TriviaGame.process_guess: Someone won.")
                self.stopGame=True
                yield from self.bot.send_message( self.channel, content="We have a winner ! Congratulations {} !".format(author.mention) )

            #required to be last for synchro
            self.guessed.set()
            self.guess_lock.release()

        else:
            self.guess_lock.release()

        return


    def internal_die_notice(self):
        if self.dieNotif_sent:
            loc_log.debug("TriviaGame.internal_die_notice: A 'die' notification has already been sent, ignoring.")
            return
        loc_log.debug("TriviaGame.internal_die_notice: Sending 'die' notification to free current channel.")
        asyncio.async( self.manager.internal_game_die_management(self) )
        self.dieNotif_sent=True
        return
        

    def get_leaderboard_string(self, mid_game=True):
        """This method returns a formated str representing the current scores/leaderboard"""


        category="category `{}`".format(self.category) if self.category else "no category"
        res="This trivia game has {}, and requires `{}` points to win. Current leaderboard:".format(category,self.winReq) if mid_game else "Leaderboard:"

        if len(self.scores.keys())==0:
            res+="\n No one scored a point yet!"
            return res

        #compute left column width
        lc_width= max( len(x.nick if x.nick else x.name) for x in self.scores )
        for user,score in self.scores.items():
            display_name= user.nick if user.nick else user.name
            display_name+= " "*( lc_width - len(display_name) )
            res+="\n**{}:** {} points".format(display_name,score)
        
        return res


    @asyncio.coroutine
    def message_leaderboard(self, mid_game=True):
        loc_log.info("TriviaGame.message_leaderboard: The leaderboard was requested.")
        yield from self.bot.send_message(self.channel, content="This trivia is over ! " + self.get_leaderboard_string(mid_game) )
        return




class TriviaManager:
    """A cog to process trivia commands and forward necessary inputs to TriviaGame"""

    def __init__(self,bot):
        self.bot=bot
        self.lock=asyncio.Lock()    #"semaphore" for gameDict. It is NOT thread safe, only coroutine safe !!!
        self.gameDict= {}           #dictionary of registered games. key: Discord.Channel, object: TriviaGame
        loc_log.info("TriviaManager initialized.")
        return


    @asyncio.coroutine
    def gameDict_safeAdd(self,key,value, timeout=10, feedback_channel=None):
        try:
            yield from asyncio.wait_for( self.lock.acquire(), timeout )
        except asyncio.TimeoutError:
            loc_log.exception("TriviaManager.gameDict_safeAdd: Could not acquire gameDict lock, returning False.")
            if feedback_channel:
                errMsg="TriviaManager: Could not acquire gameDict lock (add operation), someone else probably crashed?"
                yield from self.bot.send_message(feedback_channel, content=errMsg)

            return False

        self.gameDict[key]=value
        self.lock.release()
        return True


    @asyncio.coroutine
    def gameDict_safePop(self,key,timeout=10,feedback_channel=None):
        try:
            yield from asyncio.wait_for( self.lock.acquire(), timeout )
        except asyncio.TimeoutError:
            loc_log.exception("TriviaManager.gameDict_safePop: Could not acquire gameDict lock, raising asyncio.TimeoutError.")
            if feedback_channel:
                errMsg="TriviaManager: Could not acquire gameDict lock (pop operation), someone else probably crashed?"
                yield from self.bot.send_message(feedback_channel, content=errMsg)

            raise

            return None

        ret=self.gameDict.pop(key)
        self.lock.release()
        return ret


    @asyncio.coroutine
    def on_message(self,message):
        if not message.author.bot and self.gameDict.get(message.channel):
            game=self.gameDict[message.channel]
            if game.allowGuesses:
                loc_log.info("TriviaManager.on_message: Received a potential guess, transmitting.\n")
                #tmp="`{}` sent by `{}` with nick `{}`".format(message.content, message.author.name, message.author.nick)
                #yield from self.bot.send_message(message.channel, content=tmp)    #simple echo for testing purpose
                yield from game.process_guess(message.author, message.content, message.timestamp)
            else:
                #explicitly tell message.author his "answer" was ignored for the game?
                #yield from self.bot.send_message(message.channel, content="Trivia: Guesses not yet allowed") 
                #print("TriviaManager.on_message: guesses are not allowed yet")
                loc_log.info("TriviaManager.on_message: Guesses are not allowed, ignoring.\n")
        return


    @asyncio.coroutine
    def internal_game_die_management(self, game):
        #the game may not be in gameDict if it was created but failed to register because of lock issues
        loc_log.info("TriviaManager.internal_game_die_management: Received a die notice from '{}'.".format(game))
        if game.channel in self.gameDict:
            tmp=yield from asyncio.wait_for( self.gameDict_safePop(game.channel), None )
            if tmp != game:
                msg="TriviaManager: popped game doesn't match input game argument, expect more errors!"
                yield from self.bot.send_message( game.channel, content=msg)
                yield from self.bot.send_message( tmp.channel, content=msg)
                loc_log.critical("TriviaManager.internal_game_die_management: Popped game doesn't match!\n")
            else:
                loc_log.info("TriviaManager.internal_game_die_management: 'die' notice management completed normally.\n")
        else:
            loc_log.critical("TriviaManager.internal_game_die_management: Couldn't find the corresponding game with the channel key '{}'!\n".format(game.channel))
        
        return


    ### Commands for the trivia cog
    #   trivia
    #   triviaQuit
    #   triviaLeaderboard
    #   triviaCategories

    @commands.command(pass_context=True, aliases=["t"], no_pm=True)
    @asyncio.coroutine
    def trivia(self, ctx, *args):
    #def trivia(self,ctx, winReq : int = 5, category : str = None):
        """Starts a trivia game"""

        #Check channel type. This should be redundant with api wrapper
        if ctx.message.channel.type != discord.ChannelType.text:
            loc_log.error("TriviaManager.trivia: Command invoked in invalid channel.\n")
            yield from self.bot.say("TriviaManager: error, not invoked from a text channel")
            return
        else:
            loc_log.info("TriviaManager.trivia: Command invoked, argument processing will start.")

        #convert args from tuple to list
        args=list(args)

        #process args for a winReq
        winReq=5    #default value
        if len(args):
            for idx in [ 0, -1 ]:   #only check for 1st and last items
                try:
                    winReq=int( args[idx] )
                    args.pop(idx)
                    loc_log.debug("TriviaManager.trivia: Optional argument winReq parsed value is {}.".format(winReq))
                    break   #keep first integer found
                except ValueError:
                    pass    #the thing could not be converted to int, silently try the next one

        #process args for "noHint" flag
        #TODO
        showHints=True

        #process leftover args for a category str
        if len(args) >0:
            category=' '.join(args)
            loc_log.debug("TriviaManager.trivia: Optional argument category parsed to '{}'.".format(category))
        else:
            category=None

        #verbose feedback
        yield from self.bot.say("Trivia invoked with winReq = `{}` and category = `{}`".format(winReq,category))

        #Check if a trivia game is already running for THIS TriviaManager instance, and cancel game creation if alredy exists
        if self.gameDict.get( ctx.message.channel ):
            loc_log.warning("TriviaManager.trivia: Command invoked in a channel that already have a registered game!\n")
            yield from self.bot.say("TriviaManager: a trivia game is already running in this channel")
            return

        #game creation
        game = TriviaGame(self,ctx.message.server,ctx.message.channel,winReq,showHints,category)
        # the below task already have a built-in timeout, hence the None argument
        tmp = yield from asyncio.wait_for( self.gameDict_safeAdd( ctx.message.channel, game ), None )
        if tmp:
            # Registering game succeeded
            loc_log.info("TriviaManager.trivia: Started a new trivia game in channel '{}' and successfully registered it.\n".format(ctx.message.channel))
        else:
            # Registering game failed
            loc_log.info("TriviaManager.trivia: Trivia game in channel '{}' could not be registered, cancelling the game.\n".format(ctx.message.channel))
            yield from self.bot.say("TriviaManager: could not access protected dictionary, game cancelled")
            yield from game.stop()

        return


    @commands.command(pass_context=True, aliases=["tq"], no_pm=True)
    @asyncio.coroutine
    def triviaQuit(self, ctx, *args):
        if not self.gameDict.get( ctx.message.channel ):
            loc_log.warning("TriviaManager.triviaQuit: Command invoked in channel '{}', but no game is running.\n".format(ctx.message.channel))
            yield from self.bot.say("TriviaManager: There is no trivia game running in this channel")
            return
        loc_log.info("TriviaManager.triviaQuit: Command invoked in channel '{}'.\n".format(ctx.message.channel))
        yield from self.gameDict[ ctx.message.channel ].stop()
        return


    @commands.command(pass_context=True, aliases=["tl"], no_pm=True)
    @asyncio.coroutine
    def triviaLeaderboard(self, ctx):
        if not self.gameDict.get( ctx.message.channel ):
            loc_log.warning("TriviaManager.triviaLeaderboard: Command invoked in channel '{}', but no game is running.\n".format(ctx.message.channel))
            yield from self.bot.say("TriviaManager: There is no trivia game running in this channel")
            return
        loc_log.info("TriviaManager.triviaLeaderboard: Command invoked in channel '{}'.\n".format(ctx.message.channel))
        yield from self.gameDict[ ctx.message.channel ].message_leaderboard()
        return


    @commands.command(pass_context=True, aliases=["tc"])
    @asyncio.coroutine
    def triviaCategories(self, ctx):
        loc_log.critical("TriviaManager.triviaCategories: Command invoked in channel '{}'.\n".format(ctx.message.channel))
        yield from self.bot.say("TriviaManager: this command is not available yet.")
        #yield from self.bot.say("TriviaManager: these are the currently available categories:\n{}".format(QuestionPool.category_list_string) )
        return



def main(token):
    description="Slyfer11's trivia bot"
    bot = commands.Bot(command_prefix=commands.when_mentioned_or('>'), description=description)

    bot.add_cog(TriviaManager(bot))

    @bot.event
    @asyncio.coroutine
    def on_ready():
        print('Logged in as')
        print(bot.user.name)
        print(bot.user.id)
        print('------')


    #initialize questionPool
    QC_Manager.simple_eq = True
    QuestionPool()
    QC_Manager.simple_eq = False


    bot.run(token)


if __name__=="__main__":
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
