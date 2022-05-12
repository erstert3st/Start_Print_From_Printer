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
    __plugin_implementation__ = Start_print_from_printerPlugin()
    __plugin_hooks__ = {
        "octoprint.comm.protocol.action": __plugin_implementation__.hook_actioncommands,
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.hook_sd_list,
        "octoprint.filemanager.preprocessor": __plugin_implementation__.hook_add_local_file,
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
        # ,"octoprint.comm.protocol.scripts": __plugin_implementation__.hook_connect_printer
    }


class Start_print_from_printerPlugin(octoprint.plugin.EventHandlerPlugin,
                                     octoprint.plugin.StartupPlugin,
                                     octoprint.plugin.TemplatePlugin,
                                     octoprint.plugin.SettingsPlugin,
                                     octoprint.plugin.AssetPlugin,
                                     octoprint.plugin.SimpleApiPlugin
                                     ):

    def __init__(self):
        self._customFolderNameEdit, self._customFolderName, self._baseFolder, self._fileFolder = "", "", "", "",
        self._counter = 1
        self._longFilenameSupport = False

    def on_after_startup(self):
        global _Filemanager
        self._baseFolder = self.get_plugin_data_folder()
        self._fileFolder = self._baseFolder + "/readyFiles"
        _Filemanager = octoprint.filemanager.storage.LocalFileStorage(
            self.get_plugin_data_folder()
        )
        if self._settings.get_boolean(["firstUse"]):
            self.make_command_files(writeToSD=True, force=True)
            self.set_settings("firstUse", False)

    def get_settings_defaults(self):
        if hasattr(self, '_settings'):  # edit after button -> only y save and start ?
            tempFolderName = self._settings.get(["folder"])
            if self._customFolderName != tempFolderName:
                self._customFolderName = tempFolderName
                if(len(tempFolderName) > 6):
                    self._customFolderNameEdit = "/" + (tempFolderName[0:6] + "~1").upper() + "/"
                else:
                    self._customFolderNameEdit = tempFolderName + "/"
                # may move done check for init # may make global files

        return dict(folder="octoprint",  autoStart=False, commandsClient=False, hideFolder=False, refreshHost=False,
                    refreshSD=False, refreshNow=False,  refreshDeleteOld=False, modified=True, firstUse=True, force=False,
                    url="https://en.wikipedia.org/wiki/Hello_world")  # sendIcons=False,

    def get_template_configs(self):
        return [
            dict(type="settings",  custom_bindings=False, template="start_print_from_printer_settings.jinja2"),
        ]

    def on_event(self, event, payload):  # if event in ["FileAdded", "FileRemoved"] and payload["storage"] == "local" and "gcode" in payload["type"]:
        global _Filemanager
        if event == Events.FILE_REMOVED:  # UpdatedFiles
            path = self._fileFolder + "/" + payload['name']
            if _Filemanager.file_exists(path):
                _Filemanager.remove_file(path)
            if self._printer.is_sd_ready():
                self._printer.delete_sd_file(self._customFolderNameEdit[1:] + self.get_valid_file_name(os.path.basename(payload['name'])))  # Mark
            else:
                self.set_settings("modified", True)  # check
            return
        if event == Events.FILE_ADDED:  # UpdatedFiles may func with removed + add
            self.hook_add_local_file(path=payload['path'])
            return

    def hook_sd_list(self, comm, line, *args, **kwargs):
        if "End file list" not in line or (comm.isPrinting() and not comm.isSdPrinting()):
            return line
        if self._settings.get_boolean(["hideFolder"]):
            lengthList = len(comm._sdFiles)
            for key, file in enumerate(reversed(comm._sdFiles)):
                if(file[0].startswith(self._customFolderNameEdit)):  # Mark
                    comm._sdFiles.pop(lengthList - key - 1)
        return line

    def hook_add_local_file(self, path, file_object=None, links=None, printer_profile=None, allow_overwrite=False, *args, **kwargs):
        self.set_settings("modified", True)
        filename = dict()
        filename['file0'] = {'filename': os.path.basename(path), 'args': path, 'icon': 'shouldbeimplemented'}
        self.make_command_files(writeToSD=True, fileNameDict=filename)

    def hook_connect_printer(self, comm, script_type, script_name, *args, **kwargs):
        if not script_type == "gcode" or not script_name == "afterPrinterConnected":
            return None
  # bug LFN_WRITE LFN_WRITE
        if self._settings.get_boolean(["modified"]):
            variables = dict(myvariable=" Start transfare new Files")
            # Thread(target=self.make_command_files_wait()).start()
            return None, None, variables
        return None

    def hook_firmware_check(self, comm, cap, enabled, already_defined, *args, **kwargs):
        global _longFilenameSupport
        if cap == 'LFN_WRITE' and enabled == True:
            _longFilenameSupport = True

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

    def refresh_sd_files(self):
        self.delete_sd_files()
        self.set_settings("modified", True)
        Thread(target=self.make_command_files_wait()).start()

    def refresh_sd_data(self):
        if self._printer.is_ready():
            self._printer.commands(["M503"])

    def make_command_files_wait(self):  # use there with specific thread
        time.sleep(10)
        self.make_command_files(refreshFolder=True, writeToSD=True)

    def make_command_files(self, refreshFolder=False, writeToSD=False, deleteOldFiles=False, fileNameDict=None, force=False):
        global _Filemanager
        print("lol")
        if not fileNameDict:
            if self._settings.get_boolean(["modified"]) == False and force == False:
                return
            fileNameDict = self.get_local_files_dict(FileDestinations.LOCAL)
            self.manage_folder(_Filemanager, self._fileFolder, deleteOldFiles)

        file_obj = StreamWrapper(os.path.basename(self._fileFolder), io.BytesIO(";Generated from pluginName\n".format(**locals()).encode("ascii", "replace")))
        uploadDone = False
        # test new file with same name
        sdCommandFolder = list()
        if not deleteOldFiles and self._printer.is_sd_ready():
            self.refresh_sd_data()
            time.sleep(5)
            sdCommandFolder = list(filter(None, map(lambda x: x[1 + len(self._customFolderName):]
                                                    if x.startswith(self._customFolderName + '/') else '', list(self._printer._comm._sdFilesMap.values()))))
        for key, files in fileNameDict.items():
            uploadDone = False
            fileName = files['filename']
            pathWithFile = self._fileFolder + "/" + fileName
            if not _Filemanager.file_exists(pathWithFile) or refreshFolder:
                _Filemanager.add_file(path=pathWithFile, file_object=file_obj, allow_overwrite=True)
                with open(pathWithFile, "w") as file:
                    file.write("M118 A1 action:startPrintFromOctoPrint " + files['args'])
                # print('\x1b[6;30;42m' + key + ' wrote' + '\x1b[0m')
            if (writeToSD and self._printer.is_sd_ready()):
                uploadDone = self.upload_sd_file(filename=fileName, local_path=pathWithFile, force=force)
                time.sleep(5)
        if uploadDone:
            self.set_settings("modified", False)
# self._printer._comm -> CAPABILITY_EXTENDED_M20

    def upload_sd_file(self, local_path, filename, force, sdCommandFolder=list()):
        try:
            if not self._printer._comm.isOperational() or self._printer._comm.isBusy():
                return False
            self._printer._create_estimator("stream")
            if self._printer._comm._firmware_capabilities['LFN_WRITE']:
                filenameStart, ext = os.path.splitext(filename)
                shortFilename = filenameStart + '.gco'
            else:
                shortFilename = self.get_valid_file_name(filename)
            if not force and shortFilename in sdCommandFolder:
                return True
            self._printer._comm.startFileTransfer(
                path=local_path,
                localFilename=filename,
                remoteFilename=self._customFolderNameEdit + shortFilename,
                special=not valid_file_type(filename=filename, type="gcode"))
            return True
        except:
            return False

    def get_valid_file_name(self, filename):
        return util.get_dos_filename(
            filename,
            extension="gco",
            whitelisted_extensions=["gco", "g"]
        )

    def manage_folder(self, Filemanager, path, deleteOldFiles):
        if not Filemanager.folder_exists(path):
            Filemanager.add_folder(path)
        elif deleteOldFiles:
            Filemanager.remove_folder(path, recursive=True)
            Filemanager.add_folder(path)

    def set_settings(self, name, value=False):  # bug
        self._settings.set_boolean([name], value)
        self._settings.save()

    def delete_sd_files(self):
        existingSdFiles = list(filter(None, map(lambda x: x['name'] if x['name'].startswith(
            self._customFolderNameEdit[1:]) else '', self._printer.get_sd_files())))  # Mark
        for filename in existingSdFiles:
            self._printer.delete_sd_file(filename)

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
        global _fileNameDict
        strCounter = str(self._counter)  # test without var
        _fileNameDict['file' + strCounter] = {'filename': node['name'], 'args': "'" + node['path'] + "'", 'icon': 'shouldbeimplemented'}
        self._counter += 1

    def get_api_commands(self):
        return {
            "make_command_files": [],
        }

    def on_api_command(self, command, data):
        if command == "make_command_files":
            self.set_settings("modified", True)
            if self._settings.get_boolean(["refreshDeleteOld"]):
                self.refresh_sd_files()
            Thread(target=self.make_command_files, args=(self._settings.get_boolean(["refreshFolder"]),
                                                         self._settings.get_boolean(["writeToSD"]),
                                                         self._settings.get_boolean(["refreshDeleteOld"]),  None,
                                                         self._settings.get_boolean(["force"]))).start()
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

    def commmands(self):
        # Get all FileNames  -> check :D
        # Map and add Command -> on thinging stage -> duple [name, printCommand,May Icons] -> check :D
        # *cleanUp
        # make local Files -> check:
        # git commit -> zwischencheck
        # write to File -> check c:
        # make own Gcommands -> donne
        # get all with Foldercrap -.- check origin codde
        # Bad Info aufbohren for list Files Funcion -> FUUUUUUUUUUUUUUUUUUUUUUUUUUUCK DONE
        # make file with own Gcode -> add to File  -> done
        # let octoPrint print files -> done
        # add refresh for bugs
        # folder FUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUuCK
        # Send Map
        # option: refreshonClient add config    Folder
        # Manipulate list files + _add_files
        # rename delete -> read more other plugins!
        # uploud -> read more other plugins!
        # delete
        #  Hook into:  OR ONLY FOR BOOT Or Only by update Command ?
        # check last modified so dont update every boot -> Fuck you
        # **Revision implemented as modified
        # _add_sd_file find soluten
        # implement trigger       def add_sd_file( self, filename, path, on_success=None, on_failure=None, *args, **kwargs):
        # | Sends a custom "// action:<action> <parameters>"
        # | Sends a custom "// action:<action> <parameters>"
        # Bug in folder rename
        # Bug renaime in ready Folder ?!
        # check or learn about trigger
        # check self.vars
        # check de global vars
        # thing about boot
        # POINT OF TRUTH :D Done
        # start everything at printer connect
        # thing about run once
        # remve setting Int
        # call js function
        # add longname support  and add abfrage
        # new plugins with all setting and github
        # refresh button rething
        # CSS -.-
        # js- get value of checkboxes
        # set html right
        # check if sd file exist
        # POINT OF TRUTH :D Done
        # POINT OF TRUTH :D Done
        # remove global var force
        # fix printer connect -> may look on wwprom Editor
        #  longname support -> test all of it
        # checkVarName
        # fix Straiming bug
        # bugfrei
        # cleanup and check other plugins
        summy = "brauchst vil nd"
        # check inject vars in config.yaml may set ?
        # show foldernameEdit in Settings
        dummy = "May not possible"
        # show if octo is not connected -> may not possible
        # get good plugin name !!!!
        return "commands"
