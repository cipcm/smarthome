#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
# Copyright 2018-       Martin Sinn                         m.sinn@gmx.de
#########################################################################
#  This file is part of SmartHomeNG.    
#
#  SmartHomeNG is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SmartHomeNG is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHomeNG. If not, see <http://www.gnu.org/licenses/>.
#########################################################################


try:
    import pkg_resources
except:
    print()
    print("ERROR: setuptools are not installed")
    print("Install with 'pip3 install setuptools'")
    print()
    exit(1)


import logging
import os
import sys
import fnmatch
import datetime
import re

import pprint

from lib.utils import Utils


_shpypi_instance = None    # Pointer to the initialized instance of the Shpypi class (for use by static methods)


class Shpypi:


    def __init__(self, sh=None):
        """

        :param smarthome:

        During initialization (and initial calls to some methods, the logging interface is not yet initialized!!!
        """
        self.logger = logging.getLogger(__name__)

        global _shpypi_instance
        if _shpypi_instance is not None:
            import inspect
            curframe = inspect.currentframe()
            calframe = inspect.getouterframes(curframe, 4)
            self.logger.critical("A second 'shpypi' object has been created. There should only be ONE instance of class 'Shpypi'!!! Called from: {} ({})".format(calframe[1][1], calframe[1][3]))

        _shpypi_instance = self


        if sh is None:
            pass
        else:
            self._sh_dir = sh.get_basedir()    # anders bestimmen für tools/build_requirements.py

        return


    # --------------------------------------------------------------------------------------------
    #   Following (static) method of the class Shpypi implement the API for PyPI checking in shNG
    # --------------------------------------------------------------------------------------------

    @staticmethod
    def get_instance():
        """
        Returns the instance of the Shpypi class, to be used to access the shpypi-API

       .. code-block:: python

           from lib.shpypi import Shtime
           shtime = Shpypi.get_instance()

           # to access a method (eg. to get timezone info):
           shtime.tzinfo()


        :return: shinfo instance
        :rtype: object or None
        """
        if _shpypi_instance == None:
            return None
        else:
            return _shpypi_instance


    def get_installed_packages(self):
        """
        Returns a dict with the versions of the installed packages

        :return: dict of package and version
        :rtype: dict
        """

        installed_packages = pkg_resources.working_set

        installed_packages_dict = {}
        for dist in installed_packages:
            installed_packages_dict[dist.key] = dist.version

        # self.logger.warning("get_installed_packages: installed_packages_dict = {}".format(installed_packages_dict))
        return installed_packages_dict


    def test_requirements(self, filepath, logging=True):
        if logging:
            self.logger.info("test_requirements: filepath '{}' is checked".format(filepath))

        req_dict = self.parse_requirementsfile(filepath)
        inst_dict = self.get_installed_packages()

        requirements_met = True
        for req_pkg in req_dict:
            inst_vers = inst_dict.get(req_pkg, '-')
            min = req_dict[req_pkg].get('min', '*')
            max = req_dict[req_pkg].get('max', '*')
            if min == '*':
                min_met = True
            else:
                min_met = self._compare_versions(min, inst_vers, '<=')
            if max == '*':
                max_met = True
            else:
                max_met = self._compare_versions(inst_vers, max, '<=')

            if inst_vers == '-' or (not min_met) or (not max_met):
                requirements_met = False
                if logging:
                    if inst_vers == '-':
                        self.logger.error("test_requirements: package '{}' is not installed".format(req_pkg))
                    elif not min_met:
                        self.logger.error("test_requirements: package '{}' v{} is too old. Minimum v{} is needed".format(req_pkg, inst_vers, min))
                    else:
                        self.logger.error("test_requirements: package '{}' v{} is too new. Maximum v{} is needed".format(req_pkg, inst_vers, max))
                else:
                    if inst_vers == '-':
                        print("test_requirements: package '{}' is not installed".format(req_pkg))
                    elif not min_met:
                        print("test_requirements: package '{}' v{} is too old. Minimum v{} is needed".format(req_pkg, inst_vers, min))
                    else:
                        print("test_requirements: package '{}' v{} is too new. Maximum v{} is needed".format(req_pkg, inst_vers, max))

        return requirements_met


    def test_base_requirements(self, logging=True):

        # build an actual requirements file for core+modules
        req_files = Requirements_files()
        req_files.create_requirementsfile('base')
        req_files.create_requirementsfile('all')

        # test if the requirements of the base.txt file are met
        requirements_met = self.test_requirements(os.path.join(self._sh_dir, 'requirements', 'base.txt'), logging)

        if not requirements_met:
            if logging:
                self.logger.error("test_base_requirements: Python package requirements not met - Should terminate")
            else:
                # no logging, if called before logging is configured
                print()
                print("Python package requirements not met - SmartHomeNG is terminating")

        return requirements_met


    def parse_requirementsfile(self, file_path):
        """
        Parses the requirements file and returns the requirements as a dict

        The resulting dict has the package name as the key and the requirements string as the value

        Syntax of requirements-string:
        - operator: <, <=, ==, >=, >>
        - source: <name of plugin> or 'core'
        - version_relation: <operator><version>
        - pyversion_relation: <operator><pyversion>
        - version_relations: <version_relation>,<version_relation>
        - py_vers_requirement: <version_relations>;<pyversion_relation>
        - py_vers_requirements: <py_vers_requirement> | <py_vers_requirement>
        - requirement_string: <py_vers_requirements> (<source>)


        :param file_path: pathname to file with python requirements
        :type file_path: str

        :return: Requirements defined in the file
        :rtype: dict
        """

        # self.logger.warning("parse_requirementsfile: file_path = {}".format(file_path))
        req_dict = {}
        try:
            fobj = open(file_path)
        except:
            return req_dict

        # process file
        for rline in fobj:
            line = self._remove_comments(rline)

            if len(line) > 0:
                if ">" in line:
                    key = line[0:line.find(">")].lower().strip()
                    if key in req_dict:
                        req_dict[key] += " | " + line[line.find(">"):len(line)].lower().strip()
                    else:
                        req_dict[key] = line[line.find(">"):len(line)].lower().strip()

                elif "<" in line:
                    key = line[0:line.find("<")].lower().strip()
                    if key in req_dict:
                        req_dict[key] += " | " + line[line.find("<"):len(line)].lower().strip()
                    else:
                        req_dict[key] = line[line.find("<"):len(line)].lower().strip()

                elif "=" in line:
                    key = line[0:line.find("=")].lower().strip()
                    if key in req_dict:
                        req_dict[key] += " | " + line[line.find("="):len(line)].lower().strip()
                    else:
                        req_dict[key] = line[line.find("="):len(line)].lower().strip()

                else:
                    req_dict[line.lower().strip()] = '==*'

        fobj.close()

        result_dict = {}
        for pkg in req_dict:
            result_dict[pkg] = self._split_requirement(req_dict[pkg])
            if type(result_dict[pkg]) is list:
                self.logger.warning(" - {}: MULTIPLE requirements {}".format(pkg, result_dict[pkg]))
            # self.logger.warning(" - {}: req_str = '{}', requirements = {}".format(pkg, req_dict[pkg], result_dict[pkg]))
        # self.logger.warning("parse_requirementsfile: result_dict = {}".format(result_dict))

        return result_dict




    package_list = []  # list of packages - gets filled by get_packagelist()


    def set_packagedata(self, name, add=False):
        """
        Add a package dict to the list (if the package name does not jet exist) and return the index to that list entry

        :param name: name of the Python packahe
        :type name: str

        :return: index of the packages' dict within the list
        :rtype: int
        """
        list_index = next((index for (index, d) in enumerate(self.package_list) if d["name"] == name), None)
        if list_index == None and add:
            package = {}
            package['name'] = name
            package['vers_installed'] = '-'
            package['is_required'] = False
#            package['is_required_for_modules'] = False
            package['is_required_for_plugins'] = False
            package['is_required_for_testsuite'] = False
            package['is_required_for_docbuild'] = False
            package['required_group'] = '6';
            package['sort'] = self._build_sortstring(package)

            package['vers_req_min'] = ''
            package['vers_req_max'] = ''
            package['vers_req_msg'] = ''
            package['vers_req_source'] = ''

            package['vers_ok'] = False
            package['vers_recent'] = False
            package['pypi_version'] = ''
            package['pypi_version_ok'] = True
            package['pypi_version_not_available_msg'] = ''
            package['pypi_doc_url'] = ''


            self.package_list.append(package)
            list_index = len(self.package_list) - 1

        return list_index


    def get_packagelist(self):
        """
        Get the combined list of installed and required packages

        :return: Complete list of package date
        :rtype: list
        """

        self.package_list = []

        # process required base packages
        required_packages = self.parse_requirementsfile(os.path.join(self._sh_dir, 'requirements', 'base.txt'))
        self.logger.warning("get_packagelist: required_packages = {}".format(required_packages))

        for pkg_name in required_packages:
            if required_packages[pkg_name] != {}:   # ignore empty requirements (e.g. requirement exists only for other Python version
                index = self.set_packagedata(pkg_name, add=True)
                if index != None:
                    package = self.package_list[index]

                    package['is_required'] = True
                    package['sort'] = self._build_sortstring(package)

                    package['vers_req_min'] = required_packages[pkg_name].get('min', '*')
                    package['vers_req_max'] = required_packages[pkg_name].get('max', '*')
                    package['vers_req_msg'] = ''
                    package['vers_req_source'] = ''
                    package['sort'] = self._build_sortstring(package)


        # process installed packages
        installed_packages = self.get_installed_packages()
        self.logger.warning("get_packagelist: installed_packages = {}".format(installed_packages))
        for pkg_name in installed_packages:
            index = self.set_packagedata(pkg_name, add=True)
            if index != None:
                package = self.package_list[index]

                package['vers_installed'] = installed_packages[pkg_name]

        self.logger.warning("get_packagelist: package_list = {}".format(self.package_list))


        # process required (all) packages
        required_packages = self.parse_requirementsfile(os.path.join(self._sh_dir, 'requirements', 'all.txt'))
        self.logger.warning("get_packagelist: required_packages = {}".format(required_packages))

        for pkg_name in required_packages:
            if required_packages[pkg_name] != {}:   # ignore empty requirements (e.g. requirement exists only for other Python version
                index = self.set_packagedata(pkg_name, add=False)
                if index != None:
                    package = self.package_list[index]

                    if package['is_required'] == False:
                        package['is_required_for_plugins'] = True
                        package['sort'] = self._build_sortstring(package)

                    package['vers_req_min'] = required_packages[pkg_name].get('min', '*')
                    package['vers_req_max'] = required_packages[pkg_name].get('max', '*')
                    package['vers_req_msg'] = ''
                    package['vers_req_source'] = ''


        # process required doc-packages
        required_packages = self.parse_requirementsfile(os.path.join(self._sh_dir, 'doc', 'requirements.txt'))
        self.logger.warning("get_packagelist: required_doc_packages = {}".format(required_packages))

        for pkg_name in required_packages:
            if required_packages[pkg_name] != {}:   # ignore empty requirements (e.g. requirement exists only for other Python version
                index = self.set_packagedata(pkg_name, add=True)
                if index != None:
                    package = self.package_list[index]

                    if package['is_required'] == False:
                        package['is_required_for_docbuild'] = True
                        package['sort'] = self._build_sortstring(package)

                    if package['vers_req_min'] == '' and package['vers_req_max'] == '':
                        package['vers_req_min'] = required_packages[pkg_name].get('min', '*')
                        package['vers_req_max'] = required_packages[pkg_name].get('max', '*')
                    package['vers_req_msg'] = ''
                    package['vers_req_source'] = ''


        # process required test-packages
        required_packages = self.parse_requirementsfile(os.path.join(self._sh_dir, 'requirements', 'test.txt'))
        self.logger.warning("get_packagelist: required_test_packages = {}".format(required_packages))

        for pkg_name in required_packages:
            if required_packages[pkg_name] != {}:   # ignore empty requirements (e.g. requirement exists only for other Python version
                index = self.set_packagedata(pkg_name, add=True)
                package = self.package_list[index]

                if package['is_required'] == False:
                    package['is_required_for_testsuite'] = True
                    package['sort'] = self._build_sortstring(package)

                if package['vers_req_min'] == '' and package['vers_req_max'] == '':
                    package['vers_req_min'] = required_packages[pkg_name].get('min', '*')
                    package['vers_req_max'] = required_packages[pkg_name].get('max', '*')
                package['vers_req_msg'] = ''
                package['vers_req_source'] = ''

        self.pypi_timeout = 4
        # check if pypi service is reachable
        if self.pypi_timeout <= 0:
            pypi_available = False
            #            pypi_unavailable_message = translate('PyPI Prüfung deaktiviert')
            pypi_unavailable_message = 'PyPI Prüfung deaktiviert'
        else:
            pypi_available = True
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.pypi_timeout)
                #                sock.connect(('pypi.python.org', 443))
                sock.connect(('pypi.org', 443))
                sock.close()
            except:
                pypi_available = False
                #                pypi_unavailable_message = translate('PyPI nicht erreichbar')
                pypi_unavailable_message = 'PyPI nicht erreichbar'

        # look for PyPI data of the packages
        import xmlrpc
        pypi = xmlrpc.client.ServerProxy('https://pypi.org/pypi')
        for package in self.package_list:

            ###
            if pypi_available:
                try:
                    available = pypi.package_releases(package['name'])  # (dist.project_name)
                    self.logger.debug(
                        "pypi_json: pypi package: project_name {}, availabe = {}".format(package['name'], available))
                    try:
                        package['pypi_version'] = available[0]
                        package['pypi_version_not_available_msg'] = ""
                        package['pypi_version_ok'] = True
                        package['pypi_doc_url'] = 'https://pypi.org/pypi/' + package['name']

                    except:
                        package['pypi_version_not_available_msg'] = '?'
                        package['pypi_version_ok'] = False
                        package['pypi_doc_url'] = ''

                except:
                    package['pypi_version'] = '--'
                    #                        pkg['pypi_version_not_available_msg'] = [translate('Keine Antwort von PyPI')]
                    package['pypi_version_not_available_msg'] = ['Keine Antwort von PyPI']
            else:
                package['pypi_version_not_available_msg'] = pypi_unavailable_message
            ###

            # check if installed version is ok and recent
            if package['vers_installed'] != '-':
                min = package['vers_req_min']
                max = package['vers_req_max']
                recent = package['pypi_version']
                inst_vers = package['vers_installed']
                if min == '*':
                    min_met = True
                else:
                    min_met = self._compare_versions(min, inst_vers, '<=')
                if max == '*':
                    max_met = True
                else:
                    max_met = self._compare_versions(inst_vers, max, '<=')
                if min_met and max_met:
                    package['vers_ok'] = True
                recent_met = self._compare_versions(inst_vers, recent, '==')
                if recent_met:
                    package['vers_recent'] = True
                if max != '*':
                    pypi_ok = self._compare_versions(recent, max, '<=')
                    if not pypi_ok:
                        package['pypi_version_ok'] = False

        sorted_package_list = sorted(self.package_list, key=lambda k: k['sort'], reverse=False)
        return sorted_package_list



    def _build_sortstring(self, package):
        """
        Build and return the sort string, based on on the is_required_* elements of the requirements dict

        :param package: package requirements
        :type package: dict

        :return: sortstring
        :rtype: str
        """
        result = ''
        if package['is_required']:
            result = '1'
#        elif package['is_required_for_modules']:
#            result = '2'
        elif package['is_required_for_plugins']:
            result = '3'
        elif package['is_required_for_testsuite']:
            result = '4'
        elif package['is_required_for_docbuild']:
            result = '5'
        else:
            result = '6'

        package['required_group'] = result
        result += package['name']
        return result


    def _remove_comments(self, rline):
        """
        :param rline: line from which comments are to be removed
        :type rline: str

        :return: processed line
        :rtype: str
        """
        line = ''
        if len(rline) > 0:
            # remove comments ans strip leading-/trailing spaces
            if rline.find('#') == -1:
                line = rline
            else:
                line = rline[0:rline.find("#")]
        return line.lower().strip()




    def _split_requirement(self, req_str):
        """
        Split requirement string

        :param req_str:
        :return:
        """
        pyversion = "{0}.{1}".format(sys.version_info[0], sys.version_info[1])

        # Split requirement string into list of requirements (with python version)
        requirements_list = req_str.split('|')
        result_list = []
        for i in range(0, len(requirements_list)):
            # Split requirement (with python version) into list of requirement and python version
            requirement = requirements_list[i].split(';')   # split requirement into list of requirement and pyvers requirement
            if len(requirement) == 1:
                result_list.append(self._split_requirement_to_min_max(requirement[0]))
            else:
                # python version sppecified in requirement
                for j in range(0, len(requirement)):
                    requirement[j] = requirement[j].strip()
                if requirement[1].startswith('python_version'):
                    requirement[1] = requirement[1].replace('python_version', '')

                operator, version = self._split_operator(requirement[1])
                if self._compare_versions(pyversion, version, operator):
                    result_list.append(self._split_requirement_to_min_max(requirement[0]))

        if len(result_list) > 1:
            # Hier sollten die Einträge noch konsolidiert werden
            # Vorübergehend: Eine Liste von dicts zurückliefern
            return result_list

        if len(result_list) == 0:
            return {}

        return result_list[0]



    def _split_operator(self, reqstring):
        """
        split operator and version from string

        :param reqstring: string containing operator and version
        :type reqstring: str

        :return: operator, version
        :rtype: str, str
        """
        version = ''
        if not(type(reqstring) is str):
            self.logger.warning('_split_operator: reqstring = {}'.format(reqstring))
        reqstring = reqstring.strip()
        for operator in ['==', '<=', '>=', '<', '>']:
            if reqstring.startswith(operator):
                # strip operator (and quotes)
                version = Utils.strip_quotes(reqstring[len(operator):].strip())
                break
        if version == '':
            return '', reqstring.strip()
        else:
            return operator.strip(), version.strip()



    def _split_requirement_to_min_max(self, requirement):
        result = {}
        reqs = requirement.split(',')
        for req in reqs:
            operator, version = self._split_operator(req)
            if operator in ['>=', '==', '>']:
                result['min'] = version
            if operator in ['<', '<=', '==']:
                result['max'] = version

        return result



    def _compare_versions(self, vers1, vers2, operator):
        """
        Compare two version numbers and return if the condition is met

        :param vers1:
        :param vers2:
        :param operator:
        :type vers1: str
        :type vers2: str
        :type operator: str

        :return: true if condition is met
        :rtype: bool
        """
        v1 = self._version_to_list(vers1)
        v2 = self._version_to_list(vers2)

        result = False
        if v1 == v2 and operator in ['>=', '==', '<=']:
            result = True
        if v1 < v2 and operator in ['<', '<=']:
            result = True
        if v1 > v2 and operator in ['>', '>=']:
            result = True

        self.logger.debug("_compare_versions: - - - vers1 = {}, vers2 = {}, v1 = {}, v2 = {}, operator = '{}', result = {}".format(vers1, vers2, v1, v2, operator, result))
        return result


    def _version_to_list(self, vers):
        """
        Split version number to list and get rid of non-numeric parts

        :param vers:

        :return: version as list
        :rtype: list
        """
        # create list with [major,minor,revision,build]
        vsplit = vers.split('.')
        while len(vsplit) < 4:
            vsplit.append('0')

        # get rid of non numeric parts
        vlist = []
        for v in vsplit:
            vi = 0
            try:
                vi = int(v)
            except:
                pass
            vlist.append(vi)

        return vlist



# ===================================================================================================
#
# The following class can create requirements-files for one of the following selections:
#
#  - core
#  - modules
#  - base (core + modules)
#  - plugins (all plugins in directory ../plugins
#  - all (core + modules + plugins)
#

class Requirements_files():

    _module_files = []
    _plugin_files = []
    _core_files = []  # to be a list in the future

    def __init__(self):

        self.sh_basedir = os.sep.join(os.path.realpath(__file__).split(os.sep)[:-2])
        return


    def _seperate_operator_version(self, op_vers):
        """
        Seperate operator and version number into a list of two seperate strings

        :param op_vers:

        :return: list containing 2 elements (operator, version)
        :rtype: list
        """
        op_vers = op_vers.strip()
        if op_vers.startswith('>='):
            op = '>='
            vers = op_vers[2:]
        elif op_vers.startswith('=='):
            op = '=='
            vers = op_vers[2:]
        elif op_vers.startswith('<='):
            op = '<='
            vers = op_vers[2:]
        else:
            op = ''
            vers = op_vers
        vers = vers.strip()

        return [op,vers]


    def _build_packagelist(self, requirements):
        """
        Build a list of dicts with package information

        :return: list of package-dicts
        :rtype: list
        """

        # build list of package requirement dicts
        packagelist = []
        for key in requirements:
            packaged = {}
            wrk = re.split('<|>|=', key)
            packaged['pkg'] = wrk[0].strip()
            if packaged['pkg'].startswith('#'):
                continue

            pkg = key[len(packaged['pkg']):]
            if pkg.find(';') == -1:
                # keine python_version angegeben
                packaged['py_vers'] = ''
                wrk = re.split(',', pkg)
                wrk2 = []
                for r in wrk:
                    r2 = self._seperate_operator_version(r)
                    wrk2.append(r2)
                packaged['req'] = wrk2
            else:
                # python_version angegeben
                wrk = re.split(';', pkg)
                if wrk[1].startswith('python_version'):
                    wrk[1] = wrk[1][len('python_version'):]
                packaged['py_vers'] = wrk[1]
                wrk = re.split(',', wrk[0])
                wrk2 = []
                for r in wrk:
                    r2 = self._seperate_operator_version(r)
                    wrk2.append(r2)
                packaged['req'] = wrk2

            plglist = requirements[key]
            packaged['used_by'] = requirements[key]
            packaged['key'] = packaged['pkg'] + '+' + packaged['py_vers']
            packagelist.append(packaged)

        # reassemble pip reqirements entries
        for p in packagelist:
            wrk = p['pkg']
            wrk += p['req'][0][0] + p['req'][0][1]
            if len(p['req']) > 1:
                wrk += ','+p['req'][1][0] + p['req'][1][1]
            if p['py_vers'] != '':
                wrk += ';' + 'python_version' + p['py_vers']
            p['requests'] = wrk

        return packagelist


    def _get_filelist(self, selection):

        file_list = []
        for root, dirnames, filenames in os.walk(self.sh_basedir + os.sep + selection):
            level = root.count(os.sep)
            if level < 6:  # don't search for requirements in _pv (previous versions)
                for filename in fnmatch.filter(filenames, 'requirements.txt'):
                    # print("level = {}: root = {}".format(level, root))
                    file_list.append(os.path.join(root, filename))
        return file_list


    def _build_filelists(self, selection):

        # global _module_files, _plugin_files, _core_files
        self._module_files = []
        self._plugin_files = []
        self._core_files = []         # to be a list in the future

        if selection in ['modules', 'base', 'all']:
            # build list of all modules with requirements
            self._module_files = self._get_filelist('modules')

        if selection in ['plugins','all']:
            # build list of all plugins with requirements
            self._plugin_files = self._get_filelist('plugins')

        if selection in ['core', 'base', 'all']:
            # Read core requirements
            self._core_files = self._get_filelist('lib')
        return


    def _read_requirementfile(self, fname, requirements, add_info):

        package = ''.join((fname.split(os.sep))[-2:-1])

        with open(fname) as ifile:
            for line in ifile:
                if len(line.rstrip()) != 0:
                    #                self.setdefault(line.rstrip(), []).append('SmartHomeNG ' + package)
                    requirements.setdefault(line.rstrip(), []).append(add_info + package)
        return


    def __read_requirementfiles(self):

        requirements = {}

        # Read requirements for core
        for fname in self._core_files:
            self._read_requirementfile(fname, requirements, 'SmartHomeNG-')

        # Read requirements for modules
        for fname in self._module_files:
            self._read_requirementfile(fname, requirements, 'SmartHomeNG-module ')

        # Read requirements for plugins
        for fname in self._plugin_files:
            self._read_requirementfile(fname, requirements, 'plugin ')

        return requirements


    def _consolidate_requirements(self, packagelist):

        # key = <package>+<python-version req (if specified)>
        packagelist_sorted = sorted(packagelist, key=lambda k: k['key'])

#        pprint.pprint(packagelist_sorted)

        packagelist_consolidated = []
        for p in packagelist_sorted:
            for idx, package_consolidated in enumerate(packagelist_consolidated):
                if p['key'] == package_consolidated['key']:
                    if p['req'][0][0] == package_consolidated['req'][0][0]:
                        # if operators are equal
                        if p['req'][0][0] == '>=' and (p['req'][0][1]) >= package_consolidated['req'][0][1]:
                            # if operator is == and version of p >= version of package_consolidated
                            if package_consolidated['used_by'] != p['used_by']:
                                # join list of plugins that use the package
                                pl = package_consolidated['used_by']
                                pl.extend(p['used_by'])
                                p['used_by'] = pl
                                packagelist_consolidated[idx] = p
                            break
                        else:
                            print("?gleiche? Version von {}: consolidated = {}, further = {}, used by {}".format(package_consolidated['pkg'], package_consolidated['req'][0][1], p['req'][0][1], p['used_by']))
                            break
                    elif package_consolidated['req'][0][0] == '==':
                        # if operator is ==
                        if p['req'][0][0] == '>=' and (not (package_consolidated['req'][0][1] >= p['req'][0][1])):
                            print('ERROR: Requirements cannot be reconciled')
                            print(package_consolidated['pkg'] + ': ' + package_consolidated['req'][0][0] +
                                  package_consolidated['req'][0][1] + ' is incompatible to ' + p['req'][0][0] + p['req'][0][
                                      1])
                            packagelist_consolidated.append(p)

                    elif p['req'][0][0] == '==':
                        print('p Gleichheit ' + po['req'][0][1] + ' / ' + p['req'][0][1])
            else:
                packagelist_consolidated.append(p)
        return packagelist_consolidated


    def _write_header(self, ofile, filename):
        filename = filename.ljust(25)
        ofile.write('\n')
        ofile.write('#   +-----------------------------------------------+\n')
        ofile.write('#   |                 SmartHomeNG                   |\n')
        ofile.write('#   |            DON\'T EDIT THIS FILE               |\n')
        ofile.write('#   |           THIS FILE IS GENERATED              |\n')
        ofile.write('#   |       BY tools/build_requirements.py          |\n')
        ofile.write('#   |            ON '+datetime.datetime.now().strftime('%d.%m.%Y %H:%M')+'                |\n')
        ofile.write('#   |                                               |\n')
        ofile.write('#   |               INSTALL WITH:                   |\n')
        ofile.write('#   | sudo pip3 install -r '+filename+'|\n')
        ofile.write('#   +-----------------------------------------------+\n')
        ofile.write('\n')


    def _write_resultfile(self, selection, packagelist_consolidated, requirements):

        for key in requirements:
            requirements[key] = sorted(requirements[key], key=lambda name: (len(name.split('.')), name))

        # pprint.pprint(requirements)

        filename = 'requirements' + os.sep + selection + '.txt'
        complete_filename = self.sh_basedir + os.sep + filename
        with open(complete_filename, 'w') as outfile:
            self._write_header(outfile, filename)

            for pkg in packagelist_consolidated:
                for req in pkg['used_by']:
                    outfile.write('# {}\n'.format(req))
                outfile.write('{}\n\n'.format(pkg['requests']))

        return complete_filename


    def create_requirementsfile(self, selection):
        """
        Ths method creates a requirements-file for one of the following selections:

          - core
          - modules
          - base (core + modules)
          - plugins (all plugins in directory ../plugins
          - all (core + modules + plugins)

        :param selection: 'core' | 'modules' | 'base' | 'plugins' | 'all'
        :type selection: str

        :return: None
        """

        # build list of all packages
        selection = selection.lower()
        self._build_filelists(selection)

        requirements = self.__read_requirementfiles()

        # build list of package requirement dicts
        packagelist = self._build_packagelist(requirements)

        # consolidate requirements
        packagelist_consolidated = self._consolidate_requirements(packagelist)

        return self._write_resultfile(selection, packagelist_consolidated, requirements)

