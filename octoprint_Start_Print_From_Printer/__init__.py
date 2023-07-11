# coding=utf-8
import io
import os
import time
from threading import Thread

import flask
import octoprint.filemanager.storage
import octoprint.plugin
from octoprint import util as util
from octoprint.events import Events
from octoprint.filemanager import valid_file_type
from octoprint.filemanager.destinations import FileDestinations
from octoprint.filemanager.util import StreamWrapper

__plugin_version__ = "0.0.2"
__plugin_name__ = "Start_print_from_printer Plugin"
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3
__plugin_description__ = "start gcode Files from octoprint on the printer"


def __plugin_load__():
    global __plugin_implementation__
    global _plugin
    global __plugin_hooks__
    global Filemanager
    global _fileNameDict
    global _counter
    global _longWriteSuppoort
    _counter = 1
    _longWriteSuppoort = False
    __plugin_implementation__ = Start_print_from_printerPlugin()
    __plugin_hooks__ = {"octoprint.comm.protocol.action": __plugin_implementation__.hook_actioncommands,
                        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.hook_sd_list,
                        "octoprint.filemanager.preprocessor": __plugin_implementation__.hook_add_local_file,
                        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
                        "octoprint.comm.protocol.scripts": __plugin_implementation__.hook_connect_printer}


class Start_print_from_printerPlugin(octoprint.plugin.EventHandlerPlugin,
                                     octoprint.plugin.StartupPlugin,
                                     octoprint.plugin.TemplatePlugin,
                                     octoprint.plugin.SettingsPlugin,
                                     octoprint.plugin.AssetPlugin,
                                     octoprint.plugin.SimpleApiPlugin
                                     ):

    def __init__(self):
        self._customFolderNameEdit, self._customFolderName, self._baseFolder, self._fileFolder = "", "", "", "",

    def on_after_startup(self):
        global _Filemanager
        self._baseFolder = self.get_plugin_data_folder()
        self._fileFolder = self._baseFolder + "/readyFiles"
        _Filemanager = octoprint.filemanager.storage.LocalFileStorage(self._baseFolder)
        if self._settings.get_boolean(["firstUse"]):
            self.make_command_files(writeToSD=True, force=True)
            if self._settings.get_boolean(["modified"]):
                self.set_settings("firstUse", False)

    def get_settings_defaults(self):
        global _longWriteSuppoort
        if hasattr(self, '_settings'):
            tempFolderName = self._settings.get(["folder"])
            if self._customFolderName != tempFolderName:
                self._customFolderName = tempFolderName
                if(len(tempFolderName) > 6):
                    self._customFolderNameEdit = "/" + (tempFolderName[0:6] + "~1").upper() + "/"
                else:
                    self._customFolderNameEdit = tempFolderName + "/"
        return dict(folder="octoprint",  autoStart=False, commandsClient=False, hideFolder=False, refreshHost=False,
                    refreshSD=False, refreshNow=False,  refreshDeleteOld=False, modified=True, firstUse=True, force=False,
                    url="https://en.wikipedia.org/wiki/Hello_world", longWriteSuppoort=False)  # sendIcons=False,

    def get_template_configs(self):
        return [
            dict(type="settings",  custom_bindings=False, template="start_print_from_printer_settings.jinja2"),
        ]

    def on_event(self, event, payload):
        global _Filemanager
        if event not in ["FileAdded", "FileRemoved", "FolderRemoved", "FolderAdded"]:
            return
        if event in ["FileAdded", "FileRemoved"] and payload["storage"] == "local" and "gcode" in payload["type"]:
            if event == Events.FILE_REMOVED:
                path = self._fileFolder + "/" + payload['name']
                if _Filemanager.file_exists(path):
                    _Filemanager.remove_file(path)
                if self._printer.is_sd_ready():
                    self._printer.delete_sd_file(self._customFolderNameEdit[1:] + self.get_valid_file_name(os.path.basename(payload['name'])))
                else:
                    self.set_settings("modified", True)  # check
                return
            else:
                self.hook_add_local_file(path=payload['path'])  # test
                return

    def hook_sd_list(self, comm, line, *args, **kwargs):
        if "End file list" not in line or (comm.isPrinting() and not comm.isSdPrinting()):
            return line
        if self._settings.get_boolean(["hideFolder"]):
            lengthList = len(comm._sdFiles)
            for key, file in enumerate(reversed(comm._sdFiles)):
                if(file[0].startswith(self._customFolderNameEdit)):  # test
                    comm._sdFiles.pop(lengthList - key - 1)
        return line

    def hook_add_local_file(self, path, file_object=None, links=None, printer_profile=None, allow_overwrite=False, *args, **kwargs):  # test
        self.set_settings("modified", True)
        filename = dict()
        filename['file0'] = {'filename': os.path.basename(path), 'args': path, 'icon': 'shouldbeimplemented'}
        self.make_command_files(writeToSD=True, fileNameDict=filename)

    def hook_connect_printer(self, comm, script_type, script_name, *args, **kwargs):
        if not script_type == "gcode" or not script_name == "afterPrinterConnected":
            return None
        Thread(target=self.waitToCheckVars).start()
        return None

    def hook_actioncommands(self, comm, line, command, *args, **kwargs):
        if command == None:
            return
        elif kwargs['name'] == 'startPrintFromOctoPrint':
            if kwargs['params'][0] == "'":
                if self._printer.is_ready():
                    self._printer.unselect_file()
                    try:
                        self._printer.select_file(path=kwargs['params'].replace("'", ""), sd=False, printAfterSelect=True)
                    except:
                        self.refresh_sd_files()
            elif kwargs['params'] == "refresh":
                self.refresh_sd_files()
        else:
            return

    def make_command_files_wait(self, time=10):
        time.sleep(time)
        self.make_command_files(refreshFolder=True, writeToSD=True)

    def make_command_files(self, refreshFolder=False, writeToSD=False, deleteOldFiles=False,  force=False, sdListCompare=False, fileNameDict=None):  # fix args
        global _Filemanager
        sdCommandFolder = list()
        if not fileNameDict:
            if self._settings.get_boolean(["modified"]) == False and force == False:
                return
            fileNameDict = self.get_local_files_dict(FileDestinations.LOCAL)
            self.manage_folder(_Filemanager, self._fileFolder, deleteOldFiles)

            if not deleteOldFiles and sdListCompare and self._printer.is_sd_ready():
                sdCommandFolder = self.refresh_sd_data() # bug 

        file_obj = StreamWrapper(os.path.basename(self._fileFolder), io.BytesIO(";Generated from pluginName\n".format(**locals()).encode("ascii", "replace")))
        uploadDone = False
        for key, files in fileNameDict.items():
            uploadDone = False
            fileName = files['filename']
            pathWithFile = self._fileFolder + "/" + fileName
            if not _Filemanager.file_exists(pathWithFile) or refreshFolder or deleteOldFiles:
                _Filemanager.add_file(path=pathWithFile, file_object=file_obj, allow_overwrite=True)
                with open(pathWithFile, "w") as file:
                    file.write("M118 A1 action:startPrintFromOctoPrint " + files['args'])
                if (writeToSD and self._printer.is_sd_ready()):
                    uploadDone = self.upload_sd_file(filename=fileName, local_path=pathWithFile, force=force,
                                                     sdCommandFolder=sdCommandFolder, sdListCompare=sdListCompare)
        if uploadDone:
            self.set_settings("modified", False)
        self._printer.unselect_file()
    def waitToCheckVars(self):
        global _longWriteSuppoort
        counter = 0
        _longWriteSuppoort = False
        while counter != 15:
            if 'LFN_WRITE' in self._printer._comm._firmware_capabilities:
                _longWriteSuppoort = self._printer._comm._firmware_capabilities.get('LFN_WRITE')
                break
            if 'LONG_FILENAMFN_WRITE' in self._printer._comm._firmware_capabilities:
                _longWriteSuppoort = self._printer._comm._firmware_capabilities.get('LONG_FILENAMFN_WRITE')
                break
            time.sleep(1)
            counter += 1
        _longWriteSuppoort = False
        self.set_settings("longWriteSuppoort", _longWriteSuppoort)
        # if self._settings.get_boolean(["modified"]): # test
        #     self.make_command_files(
        #         refreshFolder=self._settings.get_boolean(["refreshFolder"]),
        #         writeToSD=self._settings.get_boolean(["writeToSD"]),
        #         deleteOldFiles=self._settings.get_boolean(["refreshDeleteOld"]),
        #         force=self._settings.get_boolean(["force"]),
        #         sdListCompare=True)


    def refresh_sd_files(self):
        self.delete_sd_files()
        self.set_settings("modified", True)
        time.sleep(3)
        self.make_command_files(True, True, self._settings.get_boolean(["refreshDeleteOld"]),   self._settings.get_boolean(["force"]), True, None)

    def refresh_sd_data(self):
        # self._printer.refresh_sd_files(blocking=True) # bug
        if _longWriteSuppoort:
            sdFileList = list(filter(None, map(lambda x: self._printer._comm._sdFilesMap.get(x[0])[len(self._customFolderName) + 2:] if (
                self._customFolderName + '/') in self._printer._comm._sdFilesMap.get(x[0]) else '', self._printer._comm._sdFiles)))
        else:
            sdFileList = self.get_sd_files(True)
        return sdFileList


    def upload_sd_file(self, local_path, filename, force, sdCommandFolder=list(), sdListCompare=False):
            if not self._printer._comm.isOperational() or self._printer._comm.isBusy():
                return False
            self._printer.unselect_file()
            if _longWriteSuppoort:  # global var
                filenameStart, ext = os.path.splitext(filename)
                shortFilename = (filenameStart.replace(" ", "_") + '.gco').upper()
                #shortFilename = filenameStart + '.gco'
            else:
                shortFilename = self.get_valid_file_name(filename)
            if sdListCompare and shortFilename.upper() in sdCommandFolder:
                return True
            self._printer._comm.startFileTransfer(
                path=local_path,
                localFilename=filename,
                remoteFilename=self._customFolderNameEdit + shortFilename,
                special=not valid_file_type(filename=filename, type="gcode"))
            time.sleep(4)

            return True
#                remoteFilename=s '/' + self._customFolderName + '/' + shortFilename,

    def get_valid_file_name(self, filename):
        return util.get_dos_filename(
            filename,
            extension="gco",
            whitelisted_extensions=["gco", "g"]
        )

    def get_sd_files(self, removeFolder=False):
        if removeFolder:
            sdFiles = list(filter(None, map(lambda x: x['name'][len(self._customFolderNameEdit[1:]):]
                           if x['name'].startswith(self._customFolderNameEdit[1:]) else '', self._printer.get_sd_files())))  # Mark
        else:
            sdFiles = list(filter(None, map(lambda x: x['name'] if x['name'].startswith(self._customFolderNameEdit[1:]) else '', self._printer.get_sd_files())))
        return sdFiles

    def manage_folder(self, Filemanager, path, deleteOldFiles):
        if not Filemanager.folder_exists(path):
            Filemanager.add_folder(path)
        elif deleteOldFiles:
            Filemanager.remove_folder(path, recursive=True)
            Filemanager.add_folder(path)

    def set_settings(self, name, value=False):
        self._settings.set_boolean([name], value)
        self._settings.save()

    def delete_sd_files(self):
        existingSdFiles = self.get_sd_files()
        while len(existingSdFiles) > 0:
            for filename in existingSdFiles:
                self._printer.delete_sd_file(filename)
                time.sleep(5)
        existingSdFiles = self.get_sd_files()

    def remove_folder(self, fileList):  # put into list files # use check sub_subfolder
        for key, subNode in fileList.items():
            if subNode["type"] == "folder" and subNode["name"] == [self._customFolderName]:
                del fileList[self._customFolderName]

    def check_dict(self, dict):  # test without key # add Filter or mapping
        for key, subNode in dict.items():
            if subNode["type"] == "folder":
                self.check_dict(subNode["children"])
            else:
                self.add_to_dict(subNode)

    def get_local_files_dict(self, fileDestinations):  # add Filter or mapping
        global _fileNameDict, _counter
        _counter = 1
        _fileNameDict = dict()
        files = (self._file_manager.list_files(fileDestinations, recursive=True, force_refresh=True))['local']
        self.check_dict(files)
        if self._settings.get_boolean(["commandsClient"]):
            _fileNameDict['file0'] = {'filename': 'Refresh Files.gcode', 'args': 'refresh', 'icon': 'shouldbeimplemented'}
        return _fileNameDict

    def add_to_dict(self, node):
        global _fileNameDict, _counter
        strCounter = str(_counter)  # test without var
        _fileNameDict['file' + strCounter] = {'filename': node['name'], 'args': "'" + node['path'] + "'", 'icon': 'shouldbeimplemented'}
        _counter += 1

    def get_api_commands(self):
        return {
            "make_command_files": [],
        }

    def on_api_command(self, command, data):
        if command == "make_command_files":
            self.set_settings("modified", True)
            if self._settings.get_boolean(["refreshDeleteOld"]):
                Thread(target=self.refresh_sd_files).start()
                return
            Thread(target=self.make_command_files, args=(True, True, self._settings.get_boolean(
                ["refreshDeleteOld"]),   self._settings.get_boolean(["force"]), True, None)).start()

            # Thread(target=self.make_command_files, args=(self._settings.get_boolean(["refreshFolder"]),
            #                                              self._settings.get_boolean(["writeToSD"]),
            #                                              self._settings.get_boolean(["refreshDeleteOld"]),  None,
            #                                              self._settings.get_boolean(["force"]))).start()
   # self.make_command_files(
            #   refreshFolder=data['refreshFolder'],
            #    writeToSD=data['writeToSD'],
            #    deleteOldFiles=data['deleteOldFiles'],
            #   force=data['force'])

    def on_api_get(self, request):
        return flask.jsonify(foo="bar")

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/Start_Print_From_Printer.js"],
            "css": ["css/Start_Print_From_Printer.css"],
            "less": ["less/Start_Print_From_Printer.less"]
        }

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "Start_Print_From_Printer": {
                "displayName": "Start_print_from_printer Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "erstert3st",
                "repo": "Start_Print_From_Printer",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/erstert3st/Start_Print_From_Printer/archive/{target_version}.zip",
            }
        }