#!/usr/local/bin/python
import lsf, default, respond, performance, os, string, shutil, stat, time

def getConfig(optionMap):
    return CarmenConfig(optionMap)

class UserFilter(default.TextFilter):
    def acceptsTestSuite(self, suite):
        if isUserSuite(suite):
            return self.containsText(suite)
        else:
            return 1

architecture = os.popen("arch").readline()[:-1]

def findLSFQueue(test):
    cpuTime = performance.getTestPerformance(test)
    if cpuTime < 15:
        return "short_" + architecture
    elif cpuTime < 120:
        return architecture
    else:
        return "idle_" + architecture

def isUserSuite(suite):
    return suite.environment.has_key("CARMUSR")

class CarmenConfig(default.Config):
    def getOptionString(self):
        return "lbr:u:R:" + default.Config.getOptionString(self)
    def getFilterList(self):
        filters = default.Config.getFilterList(self)
        self.addFilter(filters, "r", performance.TimeFilter)
        self.addFilter(filters, "u", UserFilter)
        return filters
    def addFilter(self, list, optionName, filterObj):
        if self.optionMap.has_key(optionName):
            list.append(filterObj(self.optionMap[optionName]))
    def getActionSequence(self):
        if self.optionMap.has_key("rulecomp"):
            return [ CompileRules() ]
        else:
            return default.Config.getActionSequence(self)
    def getTestRunner(self):
        if self.optionMap.has_key("lprof"):
            return [ self._getTestRunner(), WaitForDispatch(), RunLProf() ]
        else:
            return self._getTestRunner()
    def _getTestRunner(self):
        if self.optionMap.has_key("l"):
            return default.Config.getTestRunner(self)
        else:
            return lsf.SubmitTest(findLSFQueue, self.optionValue("R"))
    def getTestCollator(self):
        if self.optionMap.has_key("l"):
            return default.Config.getTestCollator(self)
        else:
            return [ lsf.Wait(), lsf.MakeResourceFiles() ]
    def getTestComparator(self):
        if self.optionMap.has_key("l"):
            return default.Config.getTestComparator(self)
        else:
            return [ performance.MakeComparisons() ]
    def getTestResponder(self):
        diffLines = 30
        if self.optionMap.has_key("b"):
            return [ respond.BatchResponder(diffLines) ]
        elif self.optionMap.has_key("o"):
            return default.Config.getTestResponder(self)
        else:
            return [ respond.UNIXInteractiveResponder(diffLines) ]

def getRaveName(test):
    return test.app.getConfigValue("rave_name")

class CompileRules:
    def __init__(self, filter = None):
        self.rulesCompiled = []
        self.raveName = None
        self.filter = filter
    def __repr__(self):
        return "Compiling rules for"
    def __call__(self, test, description):
        ruleset = RuleSet(test, self.raveName)
        if ruleset.isValid() and not ruleset.name in self.rulesCompiled:
            print description + " - ruleset " + ruleset.name
            ruleset.backup()
            compiler = os.path.join(os.environ["CARMSYS"], "bin", "crc_compile")
            commandLine = compiler + " " + self.raveName + " -optimize -archs " + architecture + " " + ruleset.sourceFile
            self.rulesCompiled.append(ruleset.name)
            os.system(commandLine)
    def setUpSuite(self, suite, description):
        print description
        self.rulesCompiled = []
        if self.raveName == None:
            self.raveName = getRaveName(suite)

class RuleSet:
    def __init__(self, test, raveName):
        self.name = self.findName(test)
        if self.name != None:
            self.targetFile = os.path.join(os.environ["CARMTMP"], "crc", "rule_set", string.upper(raveName), architecture, self.name)
            self.sourceFile = os.path.join(os.environ["CARMUSR"], "crc", "source", self.name)
    def isValid(self):
        return self.name != None and os.path.isfile(self.targetFile)
    def backup(self):
        shutil.copyfile(self.targetFile, self.targetFile + ".bak")
    def findName(self, test):
        for line in open(test.makeFileName("output")).xreadlines():
            if line.find("Loading rule set") != -1:
                finalWord = string.split(line, " ")[-1]
                return finalWord.strip()
        return None
        
class UpdatedStaticRulesetFilter:
    def __init__(self, libraryFile):
        self.libraryFile = libraryFile
    def acceptsTestCase(self, test):
        ruleset = RuleSet(test, getRaveName(test))
        return ruleset.isValid() and self.modifiedTime(ruleset.targetFile) < self.modifiedTime(os.path.join(os.environ["CARMSYS"], self.libraryFile))
    def acceptsTestSuite(self, suite):
        if not isUserSuite(suite):
            return 1       
        resourceFile = open(os.path.join(suite.environment["CARMUSR"], "Resources", "CarmResources", "Customer.etab"))
        for line in resourceFile.readlines():
            if line.find(getRaveName(suite)) != -1 and line.find("UseStaticLinking") != -1:
                entry = line.split(',')[4].strip()
                return entry[1:-1] == "true"
        return 0
    def modifiedTime(self, filename):
        return os.stat(filename)[stat.ST_MTIME]

class WaitForDispatch(lsf.Wait):
    def __init__(self):
        self.eventName = "dispatch"
    def checkCondition(self, job):
        return len(job.getProcessIds()) >= 4

class RunLProf:
    def __repr__(self):
        return "Running LProf profiler on"
    def __call__(self, test, description):
        job = lsf.LSFJob(test)
        executionMachine = job.getExecutionMachine()
        print description + ", executing on " + executionMachine
        processId = job.getProcessIds()[-1]
        runLine = "cd " + os.getcwd() + "; /users/lennart/bin/gprofile " + processId
        outputFile = "prof." + processId
        processLine = "/users/lennart/bin/process_gprof " + outputFile + " > lprof." + test.app.name
        removeLine = "rm " + outputFile
        commandLine = "rsh " + executionMachine + " '" + runLine + "; " + processLine + "; " + removeLine + "'"
        os.system(commandLine)
    def setUpSuite(self, suite, description):
        pass
 
