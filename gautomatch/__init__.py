# **************************************************************************
# *
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk)
# *              Mikel Iceta (miceta@cnb.csic.es)
# *
# * MRC Laboratory of Molecular Biology (MRC-LMB)
# * National Center for Biotechnology (CNB-CSIC)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
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

import os

import pwem
import pyworkflow.utils as pwutils
from pyworkflow.config import VarTypes
from pwem.emlib.image import ImageHandler

from gautomatch.constants import *


__version__ = '3.2'
_logo = "gautomatch_logo.png"
_references = ['Zhang']


class Plugin(pwem.Plugin):
    _homeVar = GAUTOMATCH_HOME
    _pathVars = [GAUTOMATCH_HOME]
    _supportedVersions = [V0_56]
    _url = "https://github.com/scipion-em/scipion-em-gautomatch"

    @classmethod
    def _defineVariables(cls):
        cls._defineEmVar(GAUTOMATCH_HOME, f'gautomatch-{V0_56}',
                         description='Path to Gautomatch installation folder',
                         var_type=VarTypes.STRING)
        
        cls._defineVar(GAUTOMATCH, f'Gautomatch_v{V0_56}_sm30-75_cu10.1',
                         description='Gautomatch binary filename',
                         var_type=VarTypes.STRING)
        
        cls._defineVar(GAUTOMATCH_ENV_ACTIVATION, DEFAULT_ACTIVATION_CMD,
                         description='Gautomatch environment activation command',
                         var_type=VarTypes.STRING)

    @classmethod
    def getEnviron(cls):
        """ Return the environ settings to run Gautomatch programs. """
        environ = pwutils.Environ(os.environ)
        environ.update({'PATH': Plugin.getHome('bin')},
                       position=pwutils.Environ.BEGIN)
        
        return environ
    
    @classmethod
    def getGautomatchEnvActivation(cls):
        return cls.getVar(GAUTOMATCH_ENV_ACTIVATION)
    
    @classmethod
    def getDependencies(cls):
        condaActivationCmd = cls.getCondaActivationCmd()
        neededProgs = []
        if not condaActivationCmd:
            neededProgs.append('conda')
        
        return neededProgs
    
    @classmethod
    def defineBinaries(cls, env):
        from scipion.install.funcs import CondaCommandDef
        installCmd = CondaCommandDef("gautomatch", cls.getCondaActivationCmd())
        installCmd.create(extraCmds=" cudatoolkit=10.1")

        env.addPackage('gautomatch', version=V0_56,
                       tar=f'gautomatch_v{V0_56}.tgz',
                       commands=installCmd.getCommands(),
                       neededProgs=cls.getDependencies(),
                       default=True)

    @classmethod
    def getProgram(cls):
        """ Return the program binary that will be used. """
        return " ".join([
            cls.getCondaActivationCmd(),
            cls.getGautomatchEnvActivation(),
            "&& LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH &&",
            cls.getVar(GAUTOMATCH)
        ])

    @classmethod
    def runGautomatch(cls, micNameList, refStack, workDir, extraArgs, env=None,
                      runJob=None):
        """ Run Gautomatch with the given parameters.
        If micrographs are not .mrc, they will be converted.
        If runJob=None, it will use pwutils.runJob.
        """
        args = ''

        ih = ImageHandler()

        for micName in micNameList:
            # We convert the input micrograph on demand if not in .mrc
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            if micName.endswith('.mrc'):
                pwutils.createAbsLink(os.path.abspath(micName), outMic)
            else:
                ih.convert(micName, outMic)

        args += ' %s/*.mrc' % workDir

        if refStack is not None:
            args += ' -T %s' % refStack

        args += ' %s' % extraArgs

        environ = env if env is not None else cls.getEnviron()
        if runJob is None:
            pwutils.runJob(None, cls.getProgram(), args, env=environ)
        else:
            runJob(cls.getProgram(), args, env=environ)

        for micName in micNameList:
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            # After picking we can remove the temporary file.
            pwutils.cleanPath(outMic)
