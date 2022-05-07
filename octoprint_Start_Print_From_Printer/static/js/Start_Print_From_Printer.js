/*
 * View model for Start_Print_From_Printer
 *
 * Author: erster
 * License: AGPLv3
 */
$(function () {
    function Start_print_from_printerViewModel(parameters) {
        var self = this;

        self.loginState = parameters[0];
        self.settingsViewModel = parameters[1];


        self.forceRefresh = function () {
            console.warn("lol")
            OctoPrint.simpleApiCommand("Start_Print_From_Printer", "make_command_files", {
                "refreshFolder": "True",
                "writeToSD": "True",
                "deleteOldFiles": "True",
                "force": "True"
            })
                .done(function (response) {
                    if (!response) {
                        alert(response);
                    }
                });

        }
    }
    OCTOPRINT_VIEWMODELS.push({
        construct: Start_print_from_printerViewModel,
        //dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_Start_Print_From_Printer .button"]
    });
});