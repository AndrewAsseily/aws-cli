import json
from pathlib import Path
import logging
from awscli.customizations.commands import BasicCommand
from awscli.arguments import CustomArgument
import subprocess
import shlex
import re

LOG = logging.getLogger(__name__)


class TutorialManager:
    def __init__(self):
        self.tutorials = self._load_tutorials()
        self.variables = {}

    def _load_tutorials(self):
        tutorials = {}
        tutorial_index_path = Path(__file__).parent / 'tutorials.json'

        with open(tutorial_index_path) as f:
            tutorial_files = json.load(f)['tutorial_files']

        for file_name in tutorial_files:
            file_path = Path(__file__).parent / file_name
            with open(file_path) as f:
                tutorial_data = json.load(f)
                tutorials[tutorial_data['service']] = tutorial_data

        return tutorials

    def get_tutorial_list(self):
        return [
            (service, details['name'])
            for service, details in self.tutorials.items()
        ]

    def _check_dependencies(self, step, completed_steps):
        if 'depends_on' in step:
            for dependency in step['depends_on']:
                if dependency not in completed_steps:
                    print(f"This step depends on '{dependency}' which hasn't been completed yet.")
                    return False
        return True

    def run_tutorial(self, service):
        if service not in self.tutorials:
            print(f"Tutorial for {service} not found.")
            return 1

        tutorial = self.tutorials[service]
        print(f"\nWelcome to {tutorial['name']}!")
        print(tutorial['description'])

        completed_steps = []
        cleanup_steps = []

        for step in tutorial['steps']:
            if not self._run_step(step):
                print("\nTutorial ended prematurely.")
                self._run_cleanup(cleanup_steps)
                return 1
            completed_steps.append(step['id'])
            if 'cleanup' in step:
                cleanup_steps.append(step['cleanup'])

        print("\nCongratulations! You've completed all the steps.")
        print("\nNow, let's clean up the resources we created.")

        self._run_cleanup(cleanup_steps)

        print("\nTutorial completed successfully!")
        return 0

    def _run_cleanup(self, cleanup_steps):
        for cleanup in reversed(cleanup_steps):
            print(f"\n[Cleanup] {cleanup['description']}")
            command = self._replace_variables(cleanup['command'])
            print(f"$ {command}")

            # Handle compound commands (commands with &&)
            if '&&' in command:
                commands = command.split('&&')
                for cmd in commands:
                    cmd = cmd.strip()
                    result = subprocess.run(shlex.split(cmd), capture_output=True, text=True)

                    if result.stdout:
                        print(result.stdout.rstrip())
                    if result.stderr:
                        print(result.stderr.rstrip())

                    if result.returncode != 0:
                        print(f"Warning: Cleanup step failed at command: {cmd}")
                        print("You may need to manually remove the resource.")
                        break
            else:
                # Handle single commands as before
                result = subprocess.run(shlex.split(command), capture_output=True, text=True)

                if result.stdout:
                    print(result.stdout.rstrip())
                if result.stderr:
                    print(result.stderr.rstrip())

                if result.returncode != 0:
                    print(f"Warning: Cleanup step failed. You may need to manually remove the resource.")

            print("Cleanup step completed successfully.")

    def _replace_variables(self, text):
        for var_name, var_value in self.variables.items():
            text = text.replace(f"{{{var_name}}}", var_value)
        return text

    def _run_step(self, step):
        print(f"\n[{step['title']}]")
        print(step['description'])
        print(f"$ Try: {step['command']}")

        while True:
            try:
                command = input("> ").strip()

                if not command:
                    continue
                if command.lower() in ['quit', 'exit']:
                    return False
                if command.lower() == 'skip':
                    print("Skipping this step...")
                    return True

                # Validate command structure
                if 'command_validation' in step:
                    pattern = step['command_validation']['pattern']
                    if not re.match(pattern, command):
                        print(f"That's not the expected command structure. Please try: {step['command']}")
                        continue

                    # Extract variables if specified
                    if 'extract_vars' in step['command_validation']:
                        for var_name, var_pattern in step['command_validation']['extract_vars'].items():
                            match = re.search(var_pattern, command)
                            if match:
                                self.variables[var_name] = match.group(1)

                # Execute the command
                result = subprocess.run(
                    shlex.split(command),
                    capture_output=True,
                    text=True
                )

                # Print command output
                if result.stdout:
                    print(result.stdout.rstrip())
                if result.stderr:
                    print(result.stderr.rstrip())

                # Check if command was successful
                if result.returncode == 0:
                    print("\nGreat job! The command executed successfully.")
                    return True
                else:
                    # Only show hints if the command failed
                    if step.get('hints'):
                        print("\nHints:")
                        for hint in step['hints']:
                            print(f"- {hint}")
                    print(f"\nTry: {step['command']}")

            except KeyboardInterrupt:
                print("\nUse 'quit' to exit the tutorial")
                continue
            except Exception as e:
                print(f"Error executing command: {e}")


class LearnCommand(BasicCommand):
    """Interactive learning mode for AWS CLI."""

    NAME = 'learn'
    DESCRIPTION = 'Interactive tutorial for learning AWS CLI commands'
    SYNOPSIS = 'aws learn start'

    def __init__(self, session):
        super().__init__(session)
        self.tutorial_manager = TutorialManager()

    def _run_main(self, parsed_args, parsed_globals):
        LOG.debug("Running learn command with args: %s", parsed_args)
        return self._run_main_command(parsed_args, parsed_globals)

    def _run_main_command(self, parsed_args, parsed_globals):
        if getattr(parsed_args, 'command', None) == 'start':
            return self._handle_start()
        return self._display_help(parsed_args, parsed_globals)

    def _handle_start(self):
        tutorials = self.tutorial_manager.get_tutorial_list()

        print("Welcome to AWS CLI Tutorial! Choose a topic:")
        for i, (service, name) in enumerate(tutorials, 1):
            print(f"{i}. {name}")

        while True:
            try:
                choice = int(input("\n> ")) - 1
                if 0 <= choice < len(tutorials):
                    service = tutorials[choice][0]
                    self.tutorial_manager.run_tutorial(service)
                    break
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a number.")

        return 0

    @property
    def arg_table(self):
        arg_table = {}
        command = CustomArgument(
            'command',
            choices=['start'],
            help_text='Command to run',
            positional_arg=True
        )
        command.add_to_arg_table(arg_table)
        return arg_table
