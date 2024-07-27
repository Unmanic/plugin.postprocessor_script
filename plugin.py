#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic-plugins.plugin.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     03 Jul 2021, (10:07 PM)

    Copyright:
        Copyright (C) 2021 Josh Sunnex

        This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
        Public License as published by the Free Software Foundation, version 3.

        This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
        implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
        for more details.

        You should have received a copy of the GNU General Public License along with this program.
        If not, see <https://www.gnu.org/licenses/>.

"""
import json
import logging
import os
import shutil
import stat
import subprocess

from unmanic.libs.unplugins.settings import PluginSettings

# Configure plugin logger
logger = logging.getLogger("Unmanic.Plugin.postprocessor_script")


class Settings(PluginSettings):

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)
        self.settings = {
            'only_on_task_processing_success': False,
            'run_for_each_destination_file':   False,
            'input_type':                      'command',
            'script':                          '',
            'cmd':                             '',
            'args':                            '',
            'script_dependencies':             '',
        }
        self.form_settings = {
            "only_on_task_processing_success": {
                "label":       "Only run the command when the all worker processes completed successfully.",
                "description": "When this is selected, if a worker process fails, then the configured command will not be executed.",
            },
            "run_for_each_destination_file":   {
                "label":       "Run the command for each output file created by Unmanic.",
                "description": "When this is selected, the given command will be executed once for each of the files generated by Unmanic.\n"
                               "By default Unmanic will only produce a single output file, however, other postprocessor plugins are capable of producing additional\n"
                               "file movements meaning we could end up with multiple destination files.\n"
                               "Use this config option to specify if you which this plugin to execute the given command for each of these generated output files.",
            },
            "input_type":                      self.__set_input_type_form_settings(),
            "script":                          self.__set_script_form_settings(),
            "cmd":                             self.__set_cmd_form_settings(),
            "args":                            {
                "label":       "Arguments to pass to the command or script. ",
                "description": "Specify an optional list of arguments to add to the given command or script.\n"
                               "Variables may be given in this field. See below for a list of variable types.",
                "sub_setting": True,
                "input_type":  "textarea",
            },
            "script_dependencies":             self.__set_script_dependencies_form_settings(),
        }

    def __set_input_type_form_settings(self):
        values = {
            "label":          "Execution Type",
            "description":    "Specify what to execute the defined script with.",
            "input_type":     "select",
            "select_options": [
                {
                    "value": "command",
                    "label": "Command",
                }
            ],
        }
        # Add Bash executor if binary exists
        if shutil.which('bash') is not None:
            values["select_options"].append({
                "value": "bash",
                "label": "Bash Script",
            })
        # Add Python executor if binary exists
        python_executable = shutil.which('python3')
        if python_executable is not None:
            values["select_options"].append({
                "value": "python3",
                "label": "Python Script ({})".format(python_executable),
            })
        # Add NodeJS executor if binary exists
        node_executable = shutil.which('node')
        if node_executable is not None:
            values["select_options"].append({
                "value": "node",
                "label": "NodeJS Script ({})".format(node_executable),
            })
        return values

    def __set_script_form_settings(self):
        values = {
            "label":       "Script",
            "description": "Write here the script you wish to run.",
            "sub_setting": True,
            "input_type":  "textarea",
        }
        if self.get_setting('input_type') in ['command']:
            values["display"] = 'hidden'
        return values

    def __set_cmd_form_settings(self):
        values = {
            "label":       "Command or external script to execute.",
            "description": "Specify the command or full path to the script that this plugin should execute.\n"
                           "The specified command or script must be executable.\n"
                           "Variables may be given in this field. See below for a list of variable types.",
            "sub_setting": True,
        }
        if self.get_setting('input_type') not in ['command']:
            values["display"] = 'hidden'
        return values

    def __set_script_dependencies_form_settings(self):
        values = {
            "label":       "Script Dependencies file",
            "description": "",
            "sub_setting": True,
            "input_type":  "textarea",
        }
        if self.get_setting('input_type') not in ['python3', 'node']:
            values["display"] = 'hidden'
        if self.get_setting('input_type') in ['python3']:
            values["label"] = "Script requirements.txt file"
            values["description"] = "Specify dependencies in a requirements.txt file.\n" \
                                    "These will be installed prior to script execution."
        elif self.get_setting('input_type') in ['node']:
            values["label"] = "Script package.json file"
            values["description"] = "Specify dependencies in a package.json file.\n" \
                                    "These will be installed prior to script execution."
        return values


def exec_subprocess(cmd, args, cwd=None):
    """
    Execute a subprocess command

    :param cmd:
    :param args:
    :param cwd:
    :return:
    """
    full_command = "{} {}".format(cmd, args)
    if full_command.strip():
        logger.debug("Executing command: '{}'.".format(full_command))

        # Execute command
        process = subprocess.Popen(full_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   universal_newlines=True, errors='replace', shell=True, cwd=cwd)

        # Poll the process for new output until finished
        while True:
            line_text = process.stdout.readline()
            logger.debug(line_text)
            if line_text == '' and process.poll() is not None:
                break

        # Get the final output and the exit status
        var = process.communicate()[0]
        if process.returncode == 0:
            return True
        else:
            raise Exception("Failed to execute command: '{}'".format(full_command))


def get_executable_venv_python(script_dependencies, temp_working_directory, dependency_cache_directory):
    """
    Build a VENV for python
    Install all required dependencies
    Return the updated VENV python executable path

    :param script_dependencies:
    :param temp_working_directory:
    :param dependency_cache_directory:
    :return:
    """
    executable = shutil.which('python3')

    # Write dependencies file
    with open(os.path.join(temp_working_directory, "requirements.txt"), "w") as f:
        f.write(script_dependencies)

    # Set installation cache path
    cache_path = os.path.join(dependency_cache_directory, "pip")
    if not os.path.isdir(cache_path):
        os.makedirs(cache_path)

    # Create venv and update executable
    exec_subprocess("{} -m venv venv".format(executable), "", cwd=temp_working_directory)
    executable = os.path.join(temp_working_directory, "venv", "bin", "python3")

    # Install dependencies
    os.environ['PIP_CACHE_DIR'] = cache_path
    exec_subprocess("{} -m pip install -r requirements.txt".format(executable), "", cwd=temp_working_directory)

    # Return the updated executable
    return executable


def get_executable_node(script_dependencies, temp_working_directory, dependency_cache_directory):
    """
    Install all required dependencies
    Return the node executable path

    :param script_dependencies:
    :param temp_working_directory:
    :param dependency_cache_directory:
    :return:
    """
    node_executable = shutil.which('node')
    npm_executable = shutil.which('npm')

    # Write dependencies file
    with open(os.path.join(temp_working_directory, "package.json"), "w") as f:
        f.write(script_dependencies)

    # Set installation cache path
    cache_path = os.path.join(dependency_cache_directory, "node")
    if not os.path.isdir(cache_path):
        os.makedirs(cache_path)

    # Install dependencies
    exec_subprocess("{} install --cache {} --prefer-offline ".format(npm_executable, cache_path), "",
                    cwd=temp_working_directory)

    # Return the node executable
    return node_executable


def get_temp_directory(cache_file_path):
    """
    Create and return the path to a temp directory in the cache path

    :param cache_file_path:
    :return:
    """
    output_directory = os.path.join(os.path.dirname(cache_file_path), 'postprocessor_script')
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)
    return output_directory


def get_dependency_cache_directory(settings, library_id):
    """
    Return the location of the cache directory

    :param settings:
    :param library_id:
    :return:
    """
    profile_directory = settings.get_profile_directory()
    output_directory = os.path.join(profile_directory, ".dependency_cache", str(library_id))
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)
    return output_directory


def build_script(settings, data):
    """
    Export a script to a file and make it executable

    :param settings:
    :param data:
    :return:
    """
    input_type = settings.get_setting('input_type')
    script = settings.get_setting('script')
    temp_working_directory = get_temp_directory(data.get('final_cache_path'))
    script_dependencies = settings.get_setting('script_dependencies')

    # We can cache the dependency installation to avoid re-downloading them each time. Fetch the cache directory here
    dependency_cache_directory = get_dependency_cache_directory(settings, data.get('library_id'))

    # Build command specific variables
    executable = shutil.which(input_type)
    script_extension = "txt"
    if input_type in ['bash']:
        script_extension = "sh"
    if input_type in ['python', 'python3']:
        script_extension = "py"
        executable = get_executable_venv_python(script_dependencies, temp_working_directory, dependency_cache_directory)
    elif input_type in ['node']:
        script_extension = "js"
        executable = get_executable_node(script_dependencies, temp_working_directory, dependency_cache_directory)

    # Write script to file
    script_path = os.path.join(temp_working_directory, 'script.{}'.format(script_extension))
    with open(script_path, "w") as f:
        f.write(script)

    # Make script executable
    st = os.stat(script_path)
    os.chmod(script_path, st.st_mode | stat.S_IEXEC)

    # Add script to command and return
    return "{} {}".format(executable, script_path)


def on_postprocessor_task_results(data):
    """
    Runner function - provides a means for additional postprocessor functions based on the task success.

    The 'data' object argument includes:
        final_cache_path                - The path to the final cache file that was then used as the source for all destination files.
        library_id                      - The library that the current task is associated with.
        task_processing_success         - Boolean, did all task processes complete successfully.
        file_move_processes_success     - Boolean, did all postprocessor movement tasks complete successfully.
        destination_files               - List containing all file paths created by postprocessor file movements.
        source_data                     - Dictionary containing data pertaining to the original source file.

    :param data:
    :return:

    """
    # Configure settings object
    settings = Settings(library_id=data.get('library_id'))

    if settings.get_setting('only_on_task_processing_success'):
        # Ensure all worker task processes completed successfully
        if not data.get('task_processing_success'):
            # The worker task processes did not complete successfully
            return

    cmd = settings.get_setting('cmd')
    if settings.get_setting('input_type') != 'command':
        # Generate command to be executed
        cmd = build_script(settings, data)
    args = settings.get_setting('args')
    run_for_each_destination_file = settings.get_setting('run_for_each_destination_file')

    # Remove any line-breaks in args
    args = args.replace('\n', ' ').replace('\r', '')

    # Map variables to be replaced in cmd and args
    abspath = data.get('source_data', {}).get('abspath')
    source_size = os.path.getsize(abspath) if os.path.exists(abspath) else None
    variable_map = {
        '{library_id}':       str(data.get('library_id')),
        '{final_cache_path}': str(data.get('final_cache_path')),
        '{source_file_path}': str(abspath),
        '{source_file_size}': str(source_size),
    }

    # If this is to be run for each file in the destination files, loop over the 'destination_files' list;
    # Otherwise Just run the command once.
    if run_for_each_destination_file:
        for destination_file in data.get('destination_files'):
            # Set the single destination file to the 'output_file_path' mapped variable
            variable_map['{output_file_path}'] = "{}".format(destination_file)

            # Substitute all variables in the cmd and args strings
            for key in variable_map:
                value = variable_map.get(key)
                if value is None:
                    value = key
                cmd = cmd.replace(key, value)
                args = args.replace(key, value)

            logger.info("Execute command on single file '{} {}'.".format(cmd, args))
            exec_subprocess(cmd, args)
    else:
        # Set the 'output_files' mapped variable to a JSON dumped object of the 'destination_files' list
        variable_map['{output_files}'] = "{}".format(json.dumps(data.get('destination_files', [])))

        # Substitute all variables in the cmd and args strings
        for key in variable_map:
            value = variable_map.get(key)
            if value is None:
                value = key
            cmd = cmd.replace(key, value)
            args = args.replace(key, value)

        logger.info("Execute command '{} {}'.".format(cmd, args))
        exec_subprocess(cmd, args)
