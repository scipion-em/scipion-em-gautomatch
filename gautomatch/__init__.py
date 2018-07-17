# **************************************************************************
# *
# * Authors:     Grigory Sharov (sharov@igbmc.fr)
# *
# * L'Institut de genetique et de biologie moleculaire et cellulaire (IGBMC)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************
"""
This EM module contains Gautomatch auto-picking protocol 
"""

import os
import pyworkflow.em
import pyworkflow.utils as pwutils


_logo = "gautomatch_logo.png"
GAUTOMATCH_HOME = 'GAUTOMATCH_HOME'


# The following class is required for Scipion to detect this Python module
# as a Scipion Plugin. It needs to specify the PluginMeta __metaclass__
# Some function related to the underlying package binaries need to be
# implemented
class Plugin:
    __metaclass__ = pyworkflow.em.PluginMeta

    @classmethod
    def getEnviron(cls):
        """ Return the environ settings to run Gautomatch programs. """
        environ = pwutils.Environ(os.environ)
        # Take Scipion CUDA library path
        cudaLib = environ.getFirst(('GAUTOMATCH_CUDA_LIB', 'CUDA_LIB'))
        environ.addLibrary(cudaLib)

        return environ

    @classmethod
    def getActiveVersion(cls):
        """ Return the version of the Gctf binary that is currently active. """
        path = os.environ[GAUTOMATCH_HOME]
        for v in cls.getSupportedVersions():
            if v in path or v in os.path.realpath(path):
                return v
        return ''

    @classmethod
    def getSupportedVersions(cls):
        """ Return the list of supported binary versions. """
        return ['0.50', '1.06']

    @classmethod
    def validateInstallation(cls):
        """ This function will be used to check if package is
        properly installed."""
        environ = cls.getEnviron()

        missingPaths = ["%s: %s" % (var, environ[var])
                        for var in [GAUTOMATCH_HOME]
                        if not os.path.exists(environ[var])]

        return (["Missing variables:"] + missingPaths) if missingPaths else []

    @classmethod
    def getProgram(cls):
        """ Return the program binary that will be used. """
        if (not 'GAUTOMATCH' in os.environ or
            not GAUTOMATCH_HOME in os.environ):
            return None

        return os.path.join(os.environ[GAUTOMATCH_HOME], 'bin',
                            os.path.basename(os.environ['GAUTOMATCH']))

    @classmethod
    def runGautomatch(cls, micNameList, refStack, workDir, extraArgs, env=None,
                      runJob=None):
        """ Run Gautomatch with the given parameters.
        If micrographs are not .mrc, they will be converted.
        If runJob=None, it will use pwutils.runJob.
        """
        args = ''

        ih = pyworkflow.em.ImageHandler()

        for micName in micNameList:
            # We convert the input micrograph on demand if not in .mrc
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            args += ' %s' % outMic
            if micName.endswith('.mrc'):
                pwutils.createLink(micName, outMic)
            else:
                ih.convert(micName, outMic)

        if refStack is not None:
            args += ' -T %s' % refStack

        args += ' %s' % extraArgs

        environ = env if env is not None else cls.getEnviron()
        if runJob is None:
            pwutils.runJob(None, cls.getProgram(), args, env=environ)
        else:
            runJob(cls.getProgram(), args, env=environ)

        for micName in micNameList:
            # We convert the input micrograph on demand if not in .mrc
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            # After picking we can remove the temporary file.
            pwutils.cleanPath(outMic)

