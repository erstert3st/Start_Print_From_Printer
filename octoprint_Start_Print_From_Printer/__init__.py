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
    global _file_name_dict
    global _counter
    global _long_write_support
    _counter = 1
    _long_write_support = False
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
        self._custom_folder_name_edit, self._custom_folder_name, self._baseFolder, self._file_folder = "", "", "", "",

    def on_after_startup(self):
        print("huiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii2")
        global _Filemanager
        self._baseFolder = self.get_plugin_data_folder()
        self._file_folder = self._baseFolder + "/readyFiles"
        _Filemanager = octoprint.filemanager.storage.LocalFileStorage(self._baseFolder)
        if self._settings.get_boolean(["first_use"]):
            self.make_command_files(write_to_sd=True, force=True)
            if self._settings.get_boolean(["modified"]):
                self.set_settings("first_use", False)

    def get_settings_defaults(self):
        global _long_write_support
        if hasattr(self, '_settings'):
            temp_folder_name = self._settings.get(["folder"])
            if self._custom_folder_name != temp_folder_name:
                self._custom_folder_name = temp_folder_name
                if(len(temp_folder_name) > 6):
                    self._custom_folder_name_edit = "/" + (temp_folder_name[0:6] + "~1").upper() + "/"
                else:
                    self._custom_folder_name_edit = temp_folder_name + "/"
        return dict(folder="octoprint",  auto_start=False, commands_client=False, hide_folder=False, refres_host=False,
                    refresh_sd=False, refresh_now=False,  refresh_felete_old=False, modified=True, first_use=True, force=False,
                    url="https://en.wikipedia.org/wiki/Hello_world", long_write_support=False)  # sendIcons=False,

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
                path = self._file_folder + "/" + payload['name']
                if _Filemanager.file_exists(path):
                    _Filemanager.remove_file(path)
                if self._printer.is_sd_ready():
                    self._printer.delete_sd_file(self._custom_folder_name_edit[1:] + self.get_valid_file_name(os.path.basename(payload['name'])))
                else:
                    self.set_settings("modified", True)  # check
                return
            else:
                self.hook_add_local_file(path=payload['path'])  # test
                return

    def hook_sd_list(self, comm, line, *args, **kwargs):
        if "End file list" not in line or (comm.isPrinting() and not comm.isSdPrinting()):
            return line
        if self._settings.get_boolean(["hide_folder"]):
            lengthList = len(comm._sdFiles)
            for key, file in enumerate(reversed(comm._sdFiles)):
                if(file[0].startswith(self._custom_folder_name_edit)):  # test
                    comm._sdFiles.pop(lengthList - key - 1)
        return line

    def hook_add_local_file(self, path, file_object=None, links=None, printer_profile=None, allow_overwrite=False, *args, **kwargs):  # test
        self.set_settings("modified", True)
        file_name = dict()
        file_name['file0'] = {'file_name': os.path.basename(path), 'args': path, 'icon': 'shouldbeimplemented'}
        self.make_command_files(write_to_sd=True, file_name_dict=file_name)

    def hook_connect_printer(self, comm, script_type, script_name, *args, **kwargs):
        if not script_type == "gcode" or not script_name == "afterPrinterConnected":
            return None
        Thread(target=self.wait_to_check_vars).start()
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
        self.make_command_files(refresh_folder=True, write_to_sd=True)

    def make_command_files(self, refresh_folder=False, write_to_sd=False, delete_old_files=False,  force=False, sd_list_compare=False, file_name_dict=None):  # fix args
        global _Filemanager
        sd_command_folder = list()
        if not file_name_dict:
            if self._settings.get_boolean(["modified"]) == False and force == False:
                return
            file_name_dict = self.get_local_files_dict(FileDestinations.LOCAL)
            self.manage_folder(_Filemanager, self._file_folder, delete_old_files)

            if not delete_old_files and sd_list_compare and self._printer.is_sd_ready():
                sd_command_folder = self.refresh_sd_data()  # bug

        file_obj = StreamWrapper(os.path.basename(self._file_folder), io.BytesIO(";Generated from pluginName\n".format(**locals()).encode("ascii", "replace")))
        upload_done = False
        for key, files in file_name_dict.items():
            upload_done = False
            file_name = files['file_name']
            path_with_file = self._file_folder + "/" + file_name
            if not _Filemanager.file_exists(path_with_file) or refresh_folder or delete_old_files:
                _Filemanager.add_file(path=path_with_file, file_object=file_obj, allow_overwrite=True)
                with open(path_with_file, "w") as file:
                    file.write("M118 A1 action:startPrintFromOctoPrint " + files['args'])
                if (write_to_sd and self._printer.is_sd_ready()):
                    upload_done = self.upload_sd_file(file_name=file_name, local_path=path_with_file, force=force,
                                                      sd_command_folder=sd_command_folder, sd_list_compare=sd_list_compare)
        if upload_done:
            self.set_settings("modified", False)
        if self._printer._selectedFile is not None:
            self._printer.unselect_file()

    def wait_to_check_vars(self):
        global _long_write_support
        counter = 0
        _long_write_support = False
        while counter != 15:
            if 'LFN_WRITE' in self._printer._comm._firmware_capabilities:
                _long_write_support = self._printer._comm._firmware_capabilities.get('LFN_WRITE')
                break
            if 'LONG_FILENAMFN_WRITE' in self._printer._comm._firmware_capabilities:
                _long_write_support = self._printer._comm._firmware_capabilities.get('LONG_FILENAMFN_WRITE')
                break
            time.sleep(1)
            counter += 1
       # _long_write_support = False
        self.set_settings("long_write_support", _long_write_support)
        # if self._settings.get_boolean(["modified"]): # test
        #     self.make_command_files(
        #         refresh_folder=self._settings.get_boolean(["refresh_folder"]),
        #         write_to_sd=self._settings.get_boolean(["write_to_sd"]),
        #         delete_old_files=self._settings.get_boolean(["refresh_felete_old"]),
        #         force=self._settings.get_boolean(["force"]),
        #         sd_list_compare=True)

    def refresh_sd_files(self):
        self.delete_sd_files()
        self.set_settings("modified", True)
        time.sleep(3)
        self.make_command_files(True, True, self._settings.get_boolean(["refresh_felete_old"]),   self._settings.get_boolean(["force"]), True, None)

    def refresh_sd_data(self):
        # self._printer.refresh_sd_files(blocking=True) # bug
        if _long_write_support:
            sd_file_list = list(filter(None, map(lambda x: self._printer._comm._sdFilesMap.get(x[0])[len(self._custom_folder_name) + 2:] if (
                self._custom_folder_name + '/') in self._printer._comm._sdFilesMap.get(x[0]) else '', self._printer._comm._sdFiles)))
        else:
            sd_file_list = self.get_sd_files(True)
        return sd_file_list

    def upload_sd_file(self, local_path, file_name, force, sd_command_folder=list(), sd_list_compare=False):
        if not self._printer._comm.isOperational() or self._printer._comm.isBusy():
            return False
        self._printer.unselect_file()
        if _long_write_support:  # global var
            file_name_start, ext = os.path.splitext(file_name)
            short_file_name = (file_name_start.replace(" ", "_") + '.gco').upper()
            #short_file_name = file_name_start + '.gco'
        else:
            short_file_name = self.get_valid_file_name(file_name)
        if sd_list_compare and short_file_name.upper() in sd_command_folder:
            return True
        self._printer._comm.startFileTransfer(
            path=local_path,
            localFilename=file_name,
            remoteFilename=self._custom_folder_name_edit + short_file_name,
            special=not valid_file_type(filename=file_name, type="gcode"))
        time.sleep(4)

        return True
#                remotefile_name=s '/' + self._custom_folder_name + '/' + short_file_name,

    def get_valid_file_name(self, file_name):
        return util.get_dos_filename(
            file_name,
            extension="gco",
            white_listed_extensions=["gco", "g"]
        )

    def get_sd_files(self, remove_folder=False):
        if remove_folder:
            sdFiles = list(filter(None, map(lambda x: x['name'][len(self._custom_folder_name_edit[1:]):]
                           if x['name'].startswith(self._custom_folder_name_edit[1:]) else '', self._printer.get_sd_files())))  # Mark
        else:
            sdFiles = list(filter(None, map(lambda x: x['name'] if x['name'].startswith(
                self._custom_folder_name_edit[1:]) else '', self._printer.get_sd_files())))
        return sdFiles

    def manage_folder(self, Filemanager, path, delete_old_files):
        if not Filemanager.folder_exists(path):
            Filemanager.add_folder(path)
        elif delete_old_files:
            Filemanager.remove_folder(path, recursive=True)
            Filemanager.add_folder(path)

    def set_settings(self, name, value=False):
        self._settings.set_boolean([name], value)
        self._settings.save()

    def delete_sd_files(self):
        existing_sd_files = self.get_sd_files()
        while len(existing_sd_files) > 0:
            for file_name in existing_sd_files:
                self._printer.delete_sd_file(file_name)
                time.sleep(5)
        existing_sd_files = self.get_sd_files()

    def remove_folder(self, file_list):  # put into list files # use check sub_subfolder
        for key, sub_node in file_list.items():
            if sub_node["type"] == "folder" and sub_node["name"] == [self._custom_folder_name]:
                del file_list[self._custom_folder_name]

    def check_dict(self, dict):  # test without key # add Filter or mapping
        for key, sub_node in dict.items():
            if sub_node["type"] == "folder":
                self.check_dict(sub_node["children"])
            else:
                self.add_to_dict(sub_node)

    def get_local_files_dict(self, file_destinations):  # add Filter or mapping
        global _file_name_dict, _counter
        _counter = 1
        _file_name_dict = dict()
        files = (self._file_manager.list_files(file_destinations, recursive=True, force_refresh=True))['local']
        self.check_dict(files)
        if self._settings.get_boolean(["commands_client"]):
            _file_name_dict['file0'] = {'file_name': 'Refresh Files.gcode', 'args': 'refresh', 'icon': 'shouldbeimplemented'}
        return _file_name_dict

    def add_to_dict(self, node):
        global _file_name_dict, _counter
        str_counter = str(_counter)  # test without var
        _file_name_dict['file' + str_counter] = {'file_name': node['name'], 'args': "'" + node['path'] + "'", 'icon': 'shouldbeimplemented'}
        _counter += 1

    def get_api_commands(self):
        return {
            "make_command_files": [],
        }

    def on_api_command(self, command, data):
        if command == "make_command_files":
            self.set_settings("modified", True)
            if self._settings.get_boolean(["refresh_felete_old"]):
                Thread(target=self.refresh_sd_files).start()
                return
            Thread(target=self.make_command_files, args=(True, True, self._settings.get_boolean(
                ["refresh_felete_old"]),   self._settings.get_boolean(["force"]), True, None)).start()

            # Thread(target=self.make_command_files, args=(self._settings.get_boolean(["refresh_folder"]),
            #                                              self._settings.get_boolean(["write_to_sd"]),
            #                                              self._settings.get_boolean(["refresh_felete_old"]),  None,
            #                                              self._settings.get_boolean(["force"]))).start()
   # self.make_command_files(
            #   refresh_folder=data['refresh_folder'],
            #    write_to_sd=data['write_to_sd'],
            #    delete_old_files=data['delete_old_files'],
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
