#!/astro/users/tjhillis/anaconda2/bin/python2
from __future__ import print_function, division

import glob
import os
import subprocess
import sys
import telnetlib
import time

from MatchParam import MatchParam
import MyLogger

__author__ = "Tristan J. Hillis"

"""
This uses MatchParam.py to build a MATCH parameter file object.  This script grabs from symbolic links assumed to be present 
in the passed in file path.  The files that should be in the directories are a symbolic link called parameters.param, photometry.phot,
and fake_photometry.fake.  The user should be able to specify a directory like ./MatchRunner.py /to/run/directory/ or a list
directories using ./MatchRunner.py list list_of_directories.ls (file just needs to be ascii).

There should always be a MATCH photometry and fake photometry file otherwise the program will quit.  The parameter is also specified
with the symbolic link, however if this is not present then it will assume a parameter file based of of a default in the executables
directory.  Once a photometry file is made it will copy it over and make a symbolic link that will be used in the future.

This file can also be used to run a single MATCH run where you might want to more directly specify the photometry and fake files.
One does so by putting sinlge after the executable call.  If a .param file is not specified in the specified files to come then
this will code will use the default file in it's own directory and build a parameter file off of this and copy it over.

This program also supports the following MATCH flags: -dAv, -zinc (autodetected through parameter file), more to come (-full,
                                                      -ssp, -mcdata)

Ultimately, this program generates a MATCH command as a string and passes it to the MATCH server where it will be run.
"""
# Global variables
toExecutable = sys.argv[0].split("/")
toExecutable = "/".join(toExecutable[:-1]) + "/"

def main():
    args = sys.argv[1:]

    commandList = [] # holds the list of commands to be run by the send method
    
    if args[0] == 'single': # handles single runs
        commandList = singleRun(args[1:])
    elif args[0] == 'list': # handles passed in list of directories
        pass
    else: # handles the case where one directory is passed in.
        pass

    # send command to server
    send(commandList)

def singleRun(args):
    """
    Takes in a string of arguments that are required to have a ".phot" and ".fake" file followed by optional
    MATCH flags or a ".param" file.
    This will return, in a list, a string MATCH command to be sent off.
    """
    args = " ".join(args)
    if ".fake" not in args and ".phot" not in args:
        print("Missing \".phot\" and/or \".fake\" file(s)")
        sys.exit(1)

    fakeFile = None
    photFile = None
    paramFile = None
    fitName = None

    workingD = os.getcwd() + "/" # gets the directory the executable has been invoked in

    # parse arguments to extract them
    args = args.split()
    print("Arguements:", args)
    idx = [] # indices to delete after extracting the file names needed to run MATCH
    for i, arg in enumerate(args):
        if ".fake" in arg:
            print("Found fake file:", arg)
            fakeFile = arg
            idx.append(i)
        if ".phot" in arg:
            print("Found photometry file:", arg)
            photFile = arg
            idx.append(i)
        if ".param" in arg:
            print("Found parameter file:", arg)
            paramFile = arg
            idx.append(i)
        if "fit" in arg:
            print("Found fit name:", arg)
            fitName = arg
            idx.append(i)

    # delete extracted file names in args
    args = [args[i] for i in xrange(len(args)) if i not in set(idx)]
    print("Remaining arguements:", args)

    # process any other arguements
    flags = None
    if len(arg) > 0:
        flags = parse(args)
    print("Retrieved flags:", flags)

    # if there is not passed in ".param" file then generate one based off the default one in the executable directory
    param = None
    if paramFile is None: # generate ".param" file and save it in working directory.
        # sys.argv[0] gives the location of the executable
        param = MatchParam(toExecutable + "/default.param", workingD + photFile, workingD + fakeFile)
        param.save()
        paramFile = param.name
        # make symbolic link here
        if not os.path.isfile(workingD + "parameters.param"):
            subprocess.call(["ln", "-s", param.savedTo, workingD + "parameters.param"])

    else: # passed in parameter file no need to call a save on a MatchParam object (mostly used to scan for zinc)
        param = MatchParam(workingD + paramFile, workingD + photFile, workingD + fakeFile)

    if param.zinc:
        flags.append("-zinc")

    command = "" # MATCH command that will be sent to server

    # build command (explicitely shown)
    command += "calcsfh "
    command += workingD + paramFile + " "
    command += workingD + photFile + " "
    command += workingD + fakeFile + " "

    # get next fit name
    if fitName is None:
        fitName = getFitName()

    command += workingD + fitName

    # append flags to command
    for flag in flags:
        command += " " + flag

    # add forwarding to file in command
    command += " > " + fitName + ".co"

    # write in logging
    log = MyLogger.myLogger("generate commands", toExecutable + "logs/generated_commands")
    # create stripped down command (ie no working directory included)
    stripCommand = "calcsfh " + paramFile + " " + photFile + " " + fakeFile + " " + fitName + " " + " ".join(flags) \
                   + " > " + fitName + ".co"
    log.info("Generated command (%s): %s" % (os.getcwd(), stripCommand))

    #print(command)

    return [command]


def parse(args):
    """
    This will parse the remaining arguements like -dAv=X.X and returns a list to be added to the final
    MATCH command.
    """

    idx = [] # indices to delete after
    flags = [] # holds flags to be included in final MATCH command

    for i, arg in enumerate(args):
        if "-dAv=" in arg:
            val = arg.split("=")[1]
            try:
                float(val)
                flags.append(arg)
                idx.append(i)
            except ValueError:
                print("Could not convert -dAv value into a float...please check argument.")
                sys.exit(1)

        if "-mcdata" in arg:
            flags.append(arg)
            idx.append(i)

        if "-full" in arg:
            flags.append(arg)
            idx.append(i)

    args = [args[i] for i in xrange(len(args)) if i not in set(idx)] 
    if len(args) > 0:
        print("Unknown flags found:", args)
        sys.exit(1)

    return flags


def send(commandList):
    """
    Takes a MATCH command and sends it to a server and writes info to the local command.log file in the
    working directory.
    
    Opens telnet connection useing "telnetlib" python package and sends the line to port 42424
    """
    log = MyLogger.myLogger("send", toExecutable + "/logs/send_log")
    HOST = "localhost"
    PORT = 42424

    tn = telnetlib.Telnet(HOST, PORT)
    #print("sleeping")
    #time.sleep(1)
    for command in commandList:
        tn.write(command + "\r\n") # twisted server appears to need the \r\n at the end; write to port
        log.info("Sent command: %s" % command)

    # close connection cleanly
    tn.close()



def getFitName():
    """
    Looks in the current working directory and generates the next fit name (eg "fit_010")
    """
    workingD = os.getcwd() + "/"

    # gather fit_* files
    files = glob.glob(workingD + "fit_*")

    # get rid of those files with periods in their names
    idx = []
    for i, file in enumerate(files):
        if "." in file:
            idx.append(i)
    files = [files[i] for i in xrange(len(files)) if i not in set(idx)]

    # retrieve the counters on fit_* files and make them integers
    numbers = [int(files[i].split("_")[1]) for i in xrange(len(files))]

    # sort numbers in order of least to most
    numbers = sorted(numbers, key=int)

    # retrieve the next value
    nextVal = numbers[-1] + 1

    # generate the next file name
    nextFile = ""
    if nextVal < 10:
        nextFile = "fit_00%d" % nextVal
    elif nextVal < 100:
        nextFile = "fit_0%d" % nextVal
    else:
        nextFile = "fit_%d" % nextVal

    return nextFile

if __name__ == "__main__":
    main()