# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk) [2]
# *
# * [1] SciLifeLab, Stockholm University
# * [2] MRC Laboratory of Molecular Biology (MRC-LMB)
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

import os
from collections import OrderedDict

import pyworkflow.em as em
import pyworkflow.em.metadata as md
from pyworkflow.em.constants import NO_INDEX
from pyworkflow.em.convert import ImageHandler
from pyworkflow.object import ObjectWrap
import pyworkflow.utils as pwutils


COOR_DICT = OrderedDict([
             ("_x", md.RLN_IMAGE_COORD_X),
             ("_y", md.RLN_IMAGE_COORD_Y)
             ])

COOR_EXTRA_LABELS = [
    # Additional autopicking-related metadata
    md.RLN_PARTICLE_AUTOPICK_FOM,
    md.RLN_PARTICLE_CLASS,
    md.RLN_ORIENT_PSI
    ]


def rowToObject(row, obj, attrDict, extraLabels=[]):
    """ This function will convert from a XmippMdRow to an EMObject.
    Params:
        row: the XmippMdRow instance (input)
        obj: the EMObject instance (output)
        attrDict: dictionary with the map between obj attributes(keys) and
            row MDLabels in Xmipp (values).
        extraLabels: a list with extra labels that could be included
            as properties with the label name such as: _rlnSomeThing
    """
    obj.setEnabled(row.getValue(md.RLN_IMAGE_ENABLED, 1) > 0)

    for attr, label in attrDict.iteritems():
        value = row.getValue(label)
        if not hasattr(obj, attr):
            setattr(obj, attr, ObjectWrap(value))
        else:
            getattr(obj, attr).set(value)

    attrLabels = attrDict.values()

    for label in extraLabels:
        if label not in attrLabels and row.hasLabel(label):
            labelStr = md.label2Str(label)
            setattr(obj, '_' + labelStr, row.getValueAsObject(label))


def rowToCoordinate(coordRow):
    """ Create a Coordinate from a row of a meta """
    # Check that all required labels are present in the row
    if coordRow.containsAll(COOR_DICT):
        coord = em.Coordinate()
        rowToObject(coordRow, coord, COOR_DICT, extraLabels=COOR_EXTRA_LABELS)
        # Gautomatch starts _rlnClassNumber at 0, but relion at 1
        # so let's increment its value
        if coord.hasAttribute('_rlnClassNumber'):
            coord._rlnClassNumber.increment()

        micName = None

        if coordRow.hasLabel(md.RLN_MICROGRAPH_ID):
            micId = int(coordRow.getValue(md.RLN_MICROGRAPH_ID))
            coord.setMicId(micId)
            # If RLN_MICROGRAPH_NAME is not present, use the id as a name
            micName = micId

        if coordRow.hasLabel(md.RLN_MICROGRAPH_NAME):
            micName = coordRow.getValue(md.RLN_MICROGRAPH_NAME)

        coord.setMicName(micName)

    else:
        coord = None

    return coord


def readSetOfCoordinates(workDir, micSet, coordSet, suffix=None):
    """ Read from coordinates from Gautomatch .star files.
    For a micrograph: mic1.mrc, the expected coordinate file is:
    mic1_automatch.star
    Params:
        workDir: where the Gautomatch output files are located.
        micSet: the SetOfMicrographs.
        coordSet: the SetOfCoordinates that will be populated.
        suffix: input coord file suffix
    """
    if suffix is None:
        suffix = '_automatch.star'

    for mic in micSet:
        micBase = pwutils.removeBaseExt(mic.getFileName())
        fnCoords = os.path.join(workDir, micBase + suffix)
        readCoordinates(mic, fnCoords, coordSet)


def readCoordinates(mic, fileName, coordsSet):
    if os.path.exists(fileName):
        for row in md.iterRows(fileName):
            coord = rowToCoordinate(row)
            coord.setX(coord.getX())
            coord.setY(coord.getY())
            coord.setMicrograph(mic)
            coordsSet.append(coord)


class CoordStarWriter():
    """ Helper class to write a star file containing coordinates. """
    # Gautomatch cannot read default star header (with # XMIPP_STAR_1 *),
    # so we write directly to file
    HEADER = """
data_

loop_
_rlnCoordinateX #1
_rlnCoordinateY #2
_rlnAnglePsi #3
_rlnClassNumber #4
_rlnAutopickFigureOfMerit #5
    """

    def __init__(self, filename):
        self._file = open(filename, 'w')
        # Write header
        self._file.write(self.HEADER)

    def writeRow(self, x, y, psi=0, classNumber=0, autopickFom=0):
        self._file.write("%0.6f %0.6f %0.6f %d %0.6f\n"
                         % (x, y, psi, classNumber, autopickFom))   

    def close(self):
        self._file.close()


def writeDefectsFile(coordSet, outputFn):
    """ Write all coordinates in coordSet as the defects.star file
    as expected by Gautomatch. """
    csw = CoordStarWriter(outputFn)
    for coord in coordSet:
        csw.writeRow(coord.getX(), coord.getY())
    csw.close()


def writeMicCoords(mic, coordSet, outputFn):
    """ Write all the coordinates in coordSet as star file for
    micrograph mic. """
    csw = CoordStarWriter(outputFn)
    for coord in coordSet:
        csw.writeRow(coord.getX(), coord.getY(),
                     coord.getAttributeValue('_rlnAnglePsi', 0.0),
                     coord.getAttributeValue('_rlnClassNumber', 0),
                     coord.getAttributeValue('_rlnAutopickFigureOfMerit', 0.0))
    csw.close()


def writeSetOfCoordinates(workDir, coordSet, isGlobal=False):
    """ Write set of coordinates from md to star file.
    Used only for exclusive picking. Creates .star files with
    bad coordinates (for each mic) and/or a single .star file with
    global detector defects.
    """
    for mic in coordSet.iterMicrographs():
        micBase = pwutils.removeBaseExt(mic.getFileName())
        fnCoords = os.path.join(workDir, micBase + '_rubbish.star')
        writeMicCoords(mic, coordSet.iterCoordinates(mic), fnCoords)


def writeSetOfCoordinatesXmipp(posDir, coordSet, ismanual=True, scale=1):
    """ Write a pos file on metadata format for each micrograph
    on the coordSet.
    Params:
        posDir: the directory where the .pos files will be written.
        coordSet: the SetOfCoordinates that will be read."""

    boxSize = coordSet.getBoxSize() or 100
    state = 'Manual' if ismanual else 'Supervised'

    # Create a dictionary with the pos filenames for each micrograph
    posDict = {}
    for mic in coordSet.iterMicrographs():
        micIndex, micFileName = mic.getLocation()
        micName = os.path.basename(micFileName)

        if micIndex != NO_INDEX:
            micName = '%06d_at_%s' % (micIndex, micName)

        posFn = pwutils.join(posDir, pwutils.replaceBaseExt(micName, "pos"))
        posDict[mic.getObjId()] = posFn

    f = None
    lastMicId = None
    c = 0

    for coord in coordSet.iterItems(orderBy='_micId'):
        micId = coord.getMicId()

        if micId != lastMicId:
            # we need to close previous opened file
            if f:
                f.close()
                c = 0
            f = openMd(posDict[micId], state)
            lastMicId = micId
        c += 1
        if scale != 1:
            x = coord.getX() * scale
            y = coord.getY() * scale
        else:
            x = coord.getX()
            y = coord.getY()
        f.write(" %06d   1   %d  %d  %d   %06d\n"
                % (coord.getObjId(), x, y, 1, micId))

    if f:
        f.close()

    # Write config.xmd metadata
    configFn = pwutils.join(posDir, 'config.xmd')
    writeCoordsConfig(configFn, int(boxSize), state)

    return posDict.values()


def writeCoordsConfig(configFn, boxSize, state):
    """ Write the config.xmd file needed for Xmipp picker.
    Params:
        configFn: The filename were to store the configuration.
        boxSize: the box size in pixels for extraction.
        state: picker state
    """
    # Write config.xmd metadata
    print("writeCoordsConfig: state=", state)
    mdata = md.MetaData()
    # Write properties block
    objId = mdata.addObject()
    mdata.setValue(md.MDL_PICKING_PARTICLE_SIZE, int(boxSize), objId)
    mdata.setValue(md.MDL_PICKING_STATE, state, objId)
    mdata.write('properties@%s' % configFn)


def openMd(fn, state='Manual'):
    # We are going to write metadata directly to file to do it faster
    f = open(fn, 'w')
    ismanual = state == 'Manual'
    block = 'data_particles' if ismanual else 'data_particles_auto'
    s = """# XMIPP_STAR_1 *
#
data_header
loop_
 _pickingMicrographState
%s
%s
loop_
 _itemId
 _enabled
 _xcoor
 _ycoor
 _cost
 _micrographId
""" % (state, block)
    f.write(s)
    return f


def writeSetOfMicrographs(micSet, filename):
    """ Simplified function borrowed from xmipp. """
    mdata = md.MetaData()

    for img in micSet:
        objId = mdata.addObject()
        imgRow = md.Row()
        imgRow.setValue(md.MDL_ITEM_ID, long(objId))

        index, fname = img.getLocation()
        fn = ImageHandler.locationToXmipp((index, fname))
        imgRow.setValue(md.MDL_MICROGRAPH, fn)

        if img.isEnabled():
            enabled = 1
        else:
            enabled = -1
        imgRow.setValue(md.MDL_ENABLED, enabled)
        imgRow.writeToMd(mdata, objId)

    mdata.write('Micrographs@%s' % filename)
