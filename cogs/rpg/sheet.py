import collections
from os.path import isfile, join as path_join
import json

#class Sheet(collections.abc.MutableMapping):
class Sheet:
    """Performs a write/dump operation each time the value is changed."""

    outdir = 'data/rpg/'

    ###
    ### Initialization stuff
    def __init__(self,*,member=None,filename=None):
        """Valid filename have priority over member argument."""

        if isinstance(filename,str) and isfile(filename):
            self._init_from_file(filename)
        elif member!=None:
            #try default filename
            filename=path_join(Sheet.outdir,str(member))

            if isfile(filename):
                self._init_from_file(filename)
            else:
                self.data=Sheet.default_data()
                self.filename=filename
                self.data['member']=member

        else:
            print("Building from default".format(filename))
            self.filename=None
            self.data=Sheet.default_data()

        self.get = self.data.get
    


    def _init_from_file(self,filename):
        f=open(filename)
        self.data=json.load(f)
        f.close()
        self.filename=filename
        


    @staticmethod
    def default_data():
        data={"member":None, "charisma":0, "awkwardness":0, "luck":0, "strength":0, "health":100}
        return data
    ###/Initialization stuff
    ###



    def __eq__(self,other):
        return self.data['member'] == other.data['member']



    ###
    ### Write/Dump methods
    def dump_data(self):
        if self.filename:
            Sheet.dump_data_to(self.data,self.filename)
        else:
            outfile = path_join(outdir, str(self.data['member']))
            Sheet.dump_data_to(self.data,outfile)


    
    @staticmethod
    def dump_data_to(data,filename):
        f=open(filename,'w')
        json.dump(data,f, sort_keys=True, indent=4)
        f.close()
    ### Write/Dump methods
    ###



    ###
    ### Attribute management
    def set_attribute(self,attr_name,value):
        if attr_name in self.data:
            self.data[attr_name] = value
        else:
            self.new_attribute(attr_name,value)
        return


    
    def add_to_attribute(self,attr_name,value):
        if attr_name in self.data:
            self.data[attr_name] += value
        else:
            self.new_attribute(attr_name,value)
        return



    def substract_from_attribute(self,attr_name,value):
        return self.add_to_attribute(attr_name,-value)



    def new_attribute(self,attr_name,value=None):
        __doc__="new_attribute(attr_name,value=None): Attempts to add a new attribute with initial value.\n Returns True in case of success, False if the key already exists are attr_name is not an instance of str."

        if not isinstance(attr_name,str) or attr_name in self.data:
            return False

        self.data[attr_name] = value
        return self.dump_data()


    
    def delete_attribute(self,attr_name):
        if not attr_name in self.data:
            return False
        
        return self.data.pop(attr_name)
    ###/Attribute management
    ###


        
