helpDescription = """
The MpsSolver configuration is based on the Carmen configuration. """ 

helpOptions = """-memstat version,version:limit    Give memory statistics
    Print only tests with difference larger than limit
    
-perfstat version,version:limit    Give performance statistics
    Print only tests with difference larger than limit
-feasstat version,version          Give infeasibility statistics

"""

helpScripts = """
"""

import unixConfig, carmen, os, shutil, filecmp, optimization, string, plugins, comparetest, performance

def getConfig(optionMap):
    return MpsSolverConfig(optionMap)

class MpsSolverConfig(carmen.CarmenConfig):
    def __init__(self, optionMap):
        carmen.CarmenConfig.__init__(self, optionMap)
    def getArgumentOptions(self):
        options = carmen.CarmenConfig.getArgumentOptions(self)
        options["memstat"] = "Show memory statistics for versions"
        options["perfstat"] = "Show performance statistics for versions"
        options["feasstat"] = "Show feasibility statistics for versions"
        return options
    def getActionSequence(self):
        if self.optionMap.has_key("memstat"):
            return [ MemoryStatisticsBuilder(self.optionValue("memstat")) ]
        if self.optionMap.has_key("perfstat"):
            return [ PerformanceStatisticsBuilder(self.optionValue("perfstat")) ]
        if self.optionMap.has_key("feasstat"):
            return [ FeasibilityStatisticsBuilder(self.optionValue("feasstat")) ]
        return carmen.CarmenConfig.getActionSequence(self)
    def getTestComparator(self):
        return MakeComparisons(self.optionMap.has_key("n"))
    def getQueuePerformancePrefix(self, test, arch):
        if not os.environ.has_key("MPSSOLVER_LSFQUEUE_PREFIX"):
            return carmen.CarmenConfig.getQueuePerformancePrefix(self, test, arch)
        if arch == "powerpc" or arch == "parisc_2_0":
            return ""
        else:
            return os.environ["MPSSOLVER_LSFQUEUE_PREFIX"] + "_";
    def getExecuteCommand(self, binary, test):
        mpsFiles = self.makeMpsSymLinks(test)
        return binary + " " + self.getExecuteArguments(test, mpsFiles)
    def makeMpsSymLinks(self, test):
        #
        # We need to symlink in a temp testdir to the actual .mps files
        # so as to have unique dirs for writing .sol files etc. This is so that two tests
        # using the same .mps file has its own .sol (and .glb) file
        #
        mpsFiles = "";
        if os.environ.has_key("MPSDATA_PROBLEMS"):
            mpsFilePath = os.environ["MPSDATA_PROBLEMS"]
            for file in os.listdir(mpsFilePath):
                filecmp = file.lower()
                sourcePath = os.path.join(mpsFilePath, file)
                if filecmp.endswith(".mps"):
                    if not unixConfig.isCompressed(sourcePath):
                        mpsFiles += " " + file
                        os.symlink(sourcePath, file)
        return mpsFiles
    def getExecuteArguments(self, test, files):
        solverVersion = "1429"
        problemType = "ROSTERING"
        timeoutValue = "60"
        presolveValue = "0"
        if os.environ.has_key("MPSSOLVER_VERSION"):
            solverVersion = os.environ["MPSSOLVER_VERSION"]
        if os.environ.has_key("MPSSOLVER_PROBLEM_TYPE"):
            problemType = os.environ["MPSSOLVER_PROBLEM_TYPE"]
        if len(test.options) > 0:
            parts = test.options.split(":")
            if len(parts) > 0:
                timeoutValue = parts[0]
            if len(parts) > 1:
                presolveValue = parts[1]
        args = solverVersion + " " + problemType + " " + presolveValue + " " + timeoutValue
        return args + " " + files
    def printHelpDescription(self):
        print helpDescription
        carmen.CarmenConfig.printHelpDescription(self)
    def printHelpOptions(self, builtInOptions):
        carmen.CarmenConfig.printHelpOptions(self, builtInOptions)
        print helpOptions
    def printHelpScripts(self):
        carmen.CarmenConfig.printHelpScripts(self)
        print helpScripts

# Does the same as the basic test comparison apart from when comparing
# the performance file and the memory file
class MakeComparisons(comparetest.MakeComparisons):
    def makeTestComparison(self, test):
        return MpsSolverTestComparison(test, self.overwriteOnSuccess)

class MpsSolverTestComparison(performance.PerformanceTestComparison):
    def createFileComparison(self, test, standardFile, tmpFile, makeNew = 0):
        stem, ext = os.path.basename(standardFile).split(".", 1)
        if (stem == "memory"):
            return MemoryFileComparison(test, standardFile, tmpFile, makeNew = 0)
        elif (stem == "output"):
            return OutputFileComparison(test, standardFile, tmpFile, makeNew = 0)
        else:
            return performance.PerformanceTestComparison.createFileComparison(self, test, standardFile, tmpFile, makeNew)

class OutputFileComparison(comparetest.FileComparison):
    def __init__(self, test, standardFile, tmpFile, makeNew):
        comparetest.FileComparison.__init__(self, test, standardFile, tmpFile, makeNew)
        if os.path.isfile(self.stdCmpFile):
            self.columnFilter(self.stdCmpFile)
        self.columnFilter(self.tmpCmpFile)
    def columnFilter(self, fileName):
        tmpName = fileName + ".mpssolver_extra";
        os.rename(fileName, tmpName)
        oldFile = open(tmpName)
        newFile = open(fileName, "w")
        inTable = 0
        for line in oldFile.readlines():
            cols = line.split(" ")
            if inTable:
                if self.tableEnds(line, cols):
                    inTable = 0
                else:
                    line = string.join(cols[:-2], " ").rstrip() + os.linesep
            else:
                if self.tableStarts(line, cols):
                    inTable = 1
            newFile.write(line)
        oldFile.close()
        newFile.close()
        os.remove(tmpName)
    def tableStarts(self, line, cols):
        return string.lower(cols[-1]).strip() == "time"
    def tableEnds(self, line, cols):
        return line.strip() == ""

# Returns -1 as error value, if the file is the wrong format
def getMaxMemory(fileName):
    try:
        line = open(fileName).readline()
        start = line.find(":")
        end = line.find("M", start)
        fullName = line[start + 1:end - 1]
        return float(string.strip(fullName))
    except:
        return float(-1)

def getOutputMemory(fileName):
    if not os.path.isfile(fileName):
        return float(-1)
    try:
        line = os.popen("grep 'Maximum memory used' " + fileName).readline()
        start = line.find(":")
        end = line.find("k", start)
        fullSize = line[start + 1:end - 1]
        return int((float(string.strip(fullSize)) / 1024.0) * 10.0) / 10.0
    except:
        return float(-1)

class MemoryFileComparison(comparetest.FileComparison):
    def __init__(self, test, standardFile, tmpFile, makeNew):
        comparetest.FileComparison.__init__(self, test, standardFile, tmpFile, makeNew)
        if (os.path.exists(self.stdCmpFile)):
            self.oldMaxMemory = getMaxMemory(self.stdCmpFile)
            self.newMaxMemory = getMaxMemory(self.tmpCmpFile)
            self.percentageChange = self.calculatePercentageIncrease()
            # If we didn't understand the old memory, overwrite it
            if (self.oldMaxMemory < 0):
                os.remove(self.stdFile)
        else:
            self.newMaxMemory = getMaxMemory(self.tmpFile)
            self.oldMaxMemory = self.newMaxMemory
            self.percentageChange = 0.0
    def __repr__(self):
        baseText = comparetest.FileComparison.__repr__(self)
        if self.newResult():
            return baseText
        return baseText + "(" + self.getType() + ")"
    def getType(self):
        if self.newMaxMemory < self.oldMaxMemory:
            return "smaller"
        else:
            return "larger"
    def hasDifferences(self):
        longEnough = self.newMaxMemory > float(self.test.app.getConfigValue("minimum_memory_for_test"))
        varianceEnough = self.percentageChange > float(self.test.app.getConfigValue("memory_variation_%"))
        return longEnough and varianceEnough;
    def calculatePercentageIncrease(self):
        largest = max(self.oldMaxMemory, self.newMaxMemory)
        smallest = min(self.oldMaxMemory, self.newMaxMemory)
        if smallest == 0.0:
            return 0.0
        return ((largest - smallest) / smallest) * 100
    def saveResults(self, destFile):
        # Here we save the average of the old and new performance, assuming fluctuation
        avgMemory = round((self.oldMaxMemory + self.newMaxMemory) / 2.0, 2)
        line = open(self.tmpFile).readlines()[0]
        swapLine = open(self.tmpFile).readlines()[1]
        lineToWrite = line.replace(str(self.newMaxMemory), str(avgMemory))
        newFile = open(destFile, "w")
        newFile.write(lineToWrite)
        newFile.write(swapLine)
        os.remove(self.tmpFile)

def minsec(minFloat):
    intMin = int(minFloat)
    secPart = minFloat - intMin
    return str(intMin) + "m" + str(int(secPart * 60)) + "s"

def percentDiff(perf1, perf2):
    if perf2 != 0:
        return int((perf1 / perf2) * 100.0)
    else:
        return 0

def pad(str, padSize):
    return str.ljust(padSize)
        
class PerformanceStatisticsBuilder(plugins.Action):
    def __init__(self, argString):
        args = argString.split(":")
        versionString = args[0]
        try:
            self.limit = int(args[1])
        except:
            self.limit = 0
        versions = versionString.split(",")
        self.referenceVersion = versions[0]
        self.currentVersion = None
        if len(versions) > 1:
            self.currentVersion = versions[1]
    def setUpSuite(self, suite):
        self.suiteName = suite.name + os.linesep + "   "
    def __call__(self, test):
        refPerf = performance.getTestPerformance(test, self.referenceVersion)
        currPerf = performance.getTestPerformance(test, self.currentVersion)
        pDiff = percentDiff(currPerf, refPerf)
        if self.limit == 0 or pDiff > self.limit:
            print self.suiteName + pad(test.name, 30) + "\t", minsec(refPerf), minsec(currPerf), "\t" + str(pDiff) + "%"
            self.suiteName = "   "

def getTestMemory(test, version = None):
    stemWithApp = "output" + "." + test.app.name
    if version != None and version != "":
        stemWithApp = stemWithApp + "." + version
    fileName = os.path.join(test.abspath, stemWithApp)
    outputMemory = getOutputMemory(fileName)
    if outputMemory > 0.0:
        return outputMemory
    return -1.0
            
class MemoryStatisticsBuilder(plugins.Action):
    def __init__(self, argString):
        args = argString.split(":")
        versionString = args[0]
        try:
            self.limit = int(args[1])
        except:
            self.limit = 0
        versions = versionString.split(",")
        self.referenceVersion = versions[0]
        self.currentVersion = None
        if len(versions) > 1:
            self.currentVersion = versions[1]
    def setUpSuite(self, suite):
        self.suiteName = suite.name + os.linesep + "   "
    def __call__(self, test):
        refMem = getTestMemory(test, self.referenceVersion)
        currMem = getTestMemory(test, self.currentVersion)
        refOutput = 1
        currOutput = 1
        if refMem < 0.0:
            refMem = getMaxMemory(test.makeFileName("memory", self.referenceVersion))
            refOutput = 0
        if currMem < 0.0:
            currMem = getMaxMemory(test.makeFileName("memory", self.currentVersion))
            currOutput = 0
        pDiff = percentDiff(currMem, refMem)
        if self.limit == 0 or pDiff > self.limit:
            title = self.suiteName + pad(test.name, 30)
            self.suiteName = "   "
            if refOutput == 0 and currOutput == 0:
                print title
                return
            pDiff = str(pDiff) + "%"
            if refOutput == 0:
                refMem = "(" + str(refMem) + ")"
                pDiff = "(" + pDiff + ")"
            if currOutput == 0:
                currMem = "(" + str(currMem) + ")"
                pDiff = "(" + pDiff + ")"
            print title + "\t", refMem, currMem, "\t" + pDiff

class FeasibilityStatisticsBuilder(plugins.Action):
    def __init__(self, versionString):
        versions = versionString.split(",")
        self.referenceVersion = versions[0]
        self.currentVersion = None
        if len(versions) > 1:
            self.currentVersion = versions[1]
    def setUpSuite(self, suite):
        self.suiteName = suite.name + os.linesep + "   "
    def numInfeasibilities(self, test, version):
        fileName = test.makeFileName("errors", version)
        if not os.path.isfile(fileName):
            return 0
        grepCommand = "grep -E 'Solver fail' " + fileName
        return len(os.popen(grepCommand).readlines())
    def __call__(self, test):
        refErrors = self.numInfeasibilities(test, self.referenceVersion)
        currErrors = self.numInfeasibilities(test, self.currentVersion)
        if refErrors + currErrors > 0:
            print self.suiteName + pad(test.name, 30) + "\t", refErrors, currErrors
            self.suiteName = "   "

        
