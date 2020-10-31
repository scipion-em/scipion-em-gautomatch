=================
Gautomatch plugin
=================

This plugin provide a wrapper around `Gautomatch picker <https://www2.mrc-lmb.cam.ac.uk/research/locally-developed-software/zhang-software/>`_.

.. image:: https://img.shields.io/pypi/v/scipion-em-gautomatch.svg
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: PyPI release

.. image:: https://img.shields.io/pypi/l/scipion-em-gautomatch.svg
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: License

.. image:: https://img.shields.io/pypi/pyversions/scipion-em-gautomatch.svg
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: Supported Python versions

.. image:: https://img.shields.io/sonar/quality_gate/scipion-em_scipion-em-gautomatch?server=https%3A%2F%2Fsonarcloud.io
        :target: https://sonarcloud.io/dashboard?id=scipion-em_scipion-em-gautomatch
        :alt: SonarCloud quality gate

.. image:: https://img.shields.io/pypi/dm/scipion-em-gautomatch
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: Downloads


+--------------+----------------+--------------------+
| prod: |prod| | devel: |devel| | support: |support| |
+--------------+----------------+--------------------+

.. |prod| image:: http://scipion-test.cnb.csic.es:9980/badges/gautomatch_prod.svg
.. |devel| image:: http://scipion-test.cnb.csic.es:9980/badges/gautomatch_devel.svg
.. |support| image:: http://scipion-test.cnb.csic.es:9980/badges/gautomatch_support.svg


Installation
------------

You will need to use `3.0 <https://github.com/I2PC/scipion/releases/tag/V3.0.0>`_ version of Scipion to be able to run these protocols. To install the plugin, you have two options:

a) Stable version
   
   .. code-block::
   
      scipion installp -p scipion-em-gautomatch

b) Developer's version

   * download repository 
   
   .. code-block::
   
      git clone https://github.com/scipion-em/scipion-em-gautomatch.git

   * install 

   .. code-block::
   
      scipion installp -p path_to_scipion-em-gautomatch --devel

Gautomatch binaries will be installed automatically with the plugin, but you can also link an existing installation. 
Default installation path assumed is ``software/em/gautomatch-0.56``, if you want to change it, set *GAUTOMATCH_HOME* in ``scipion.conf`` file to the folder where the Gautomatch is installed. Depending on your CUDA version and GPU card compute capability you might want to change the default binary from ``Gautomatch_v0.56_sm30-75_cu10.1`` to a different one by explicitly setting *GAUTOMATCH* variable. If you need to use CUDA different from the one used during Scipion installation (defined by CUDA_LIB), you can add *GAUTOMATCH_CUDA_LIB* variable to the config file. Various binaries can be downloaded from the official Gautomatch website. 

To check the installation, simply run the following Scipion test:

``scipion test gautomatch.tests.test_protocols_gautomatch.TestGautomatchAutomaticPicking``

Supported versions
------------------

0.53 and 0.56

Protocols
---------

* `auto-picking <https://github.com/scipion-em/scipion-em-gautomatch/wiki/ProtGautomatch>`_

References
----------

1. Kai Zhang. Unpublished. 
