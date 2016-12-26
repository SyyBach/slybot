import asyncio


class LatexKernel(enum):
    math = 0
    text = 1



class Latex:

    preserved_count = -1
    preserved_dir = 'data/latex/preserve/'
    build_dir = 'data/latex/build/'


    def __init__(self,bot,channel,formula_str,author, *, preserve=False, name=None, kernel=None):
        self.bot=bot
        self.channel=channel
        self.formula_str=formula_str
        self.author=author
        self.completion= asyncio.Event()
        if not isinstance(kernel,LatexKernel):
            self.kernel=LatexLernel.math
        else:
            self.kernel=kernel

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
            loc_log.warning("Latex.start: return code for pdflatex subprocess non 0, rcode = '{}'.".format(rcode))
            msg="{} Could not process the latex formula !".format(self.author.mention)
            yield from self.bot.send_message(self.channel, content=msg)
            self.completion.set()
            return
        rcode,filename = self.call_convert(jobname = jobname, indir = dirname)
        if rcode != 0:
            loc_log.warning("Latex.start: return code for convert subprocess non 0, rcode = '{}'.".format(rcode))
            msg="{} Could not convert to png !".format(self.author.mention)
            yield from self.bot.send_message(self.channel, content=msg)
            self.completion.set()
            return
        loc_log.info("Latex.start: All subprocesses completed normally.")
        yield from self.send_embed_pic(filename)
        self.completion.set()
        return


    def call_latex(self):
        """Encapsulate the global call_latex function for Latex use cases."""
        if self.name:
            return call_latex( self.formula_str, self.name, Latex.build_dir[:-1], return_name=True)
        else:
            return call_latex( self.formula_str, outdir=Latex.build_dir[:-1], return_name=True )


    def call_convert(self, jobname, indir):
        """Encapsulate the global call_convert function for Latex use cases."""
        if self.name:
            return call_convert( jobname+'.pdf', indir, jobname+'.png', Latex.preserved_dir, return_name=True)
        else:
            return call_convert( jobname+'.pdf', indir, jobname+'.png', return_name=True)



    @asyncio.coroutine
    def send_embed_pic(self,filename):
        fp=open(filename,'rb')
        yield from self.bot.send_file(self.channel, fp, filename=filename, content=self.author.mention)
        fp.close()
        return




class LatexMath(Latex):
    def __init__(self, *args, **kwargs):
        super().__init__(args,kwargs)
        self.kernel = LatexKernel.math


class LatexText(Latex):
    def __init__(self, *args, **kwargs):
        super().__init__(args,kwargs)
        self.kernel = LatexKernel.text




