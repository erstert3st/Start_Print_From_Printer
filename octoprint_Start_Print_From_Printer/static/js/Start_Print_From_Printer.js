/*
 * View model for Start_Print_From_Printer
 *
 * Author: erster
 * License: AGPLv3
 */
$(function () {
    function Start_print_from_printerViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];



        self.folder = ko.observable();
        self.autoStart = ko.observable();
        self.commandsClient = ko.observable();
        self.hideFolder = ko.observable();
        self.refreshHost = ko.observable();
        self.refreshSD = ko.observable();
        self.refreshDeleteOld = ko.observable();
        // document.querySelector('#color-picker-control')

        self.forceRefresh = function () {
            saveOptions = document.querySelector('button.btn-primary:nth-child(4)');
            saveOptions.click();
            OctoPrint.simpleApiCommand("Start_Print_From_Printer", "make_command_files", {
                "refreshFolder": "True",
                "writeToSD": "True",
                "deleteOldFiles": "True",
                "force": "True"
            }).done(function (response) {
                    if (!response) {
                        showConfirmationDialog(
                            _.sprintf(
                                gettext(
                                    'You are about to restore the backup file "%(name)s". This cannot be undone.'
                                ),
                                { name: _.escape(response) }
                            )
                        );
                    }
                });

        }
        self.onSettingsShown = function () {
            // alert("lol");
        };
    }
    OCTOPRINT_VIEWMODELS.push({
        construct: Start_print_from_printerViewModel,
        elements: ['#settings_plugin_Start_Print_From_Printer .button1']
    });
});