/*
 * View model for Start_Print_From_Printer
 *
 * Author: erster
 * License: AGPLv3
 */
$(function() {
    function Start_print_from_printerViewModel(parameters)         
    var self = this;

        self.loginState = parameters[0];
        self.settings = parameters[1];
        self.forceRefresh = function () {
            alert("Something went wrong :c !!");
            OctoPrint.simpleApiCommand("HelloWorldPlugin", "make_command_files", {
                "refreshFolder": "True",
                "writeToSD": "True",
                "deleteOldFiles": "True",
                "force": "True"
            })
                .done(function (response) {
                    if (!response) {
                        alert("Something went wrong :c !!");
                    }
                });

        }
    /* view model class, parameters for constructor, container to bind to
     * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
     * and a full list of the available options.
     */
    OCTOPRINT_VIEWMODELS.push({
        construct: Start_print_from_printerViewModel,
        // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
        dependencies: [ /* "loginStateViewModel", "settingsViewModel" */ ],
        // Elements to bind to, e.g. #settings_plugin_Start_Print_From_Printer, #tab_plugin_Start_Print_From_Printer, ...
        elements: ["#settings_plugin_helloworld .button",]
    });
});
