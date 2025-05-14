"""
Tutorial Schema:
{
    "tutorials": {                              # Root object containing all tutorials
        "<service-name>": {                     # e.g., "s3", "iam", "ec2"
            "name": string,                     # Display name of the tutorial
            "description": string,              # Brief description of what will be learned
            "credentials_required": true,
            "variables": {                      # Definitions of variables used in commands
                "<variable-name>": {
                    "description": string,      # Description of what this variable represents
                    "validation_pattern": string # Regex pattern to validate variable value
                }
            },
            "prerequisites": [                   # Optional list of requirements
                {
                    "type": string,            # e.g., "permission", "resource"
                    "description": string      # What is needed
                }
            ],
            "steps": [                          # Array of tutorial steps
                {
                    "id": string,              # Unique identifier for the step
                    "title": string,           # Short title of the step
                    "description": string,     # Detailed explanation
                    "required": boolean,       # Whether this step must be completed
                    "depends_on": [            # Optional: IDs of steps that must be completed first
                        string                 # Step IDs this step depends on
                    ],
                    "command": string,         # AWS CLI command to run with {variables}
                    "command_validation": {     # How to validate the command structure
                        "pattern": string,     # Regex pattern for the full command
                        "extract_vars": {      # Variables to extract from command
                            "<var-name>": string # Regex pattern to extract variable
                        }
                    },
                    "expected_output": string, # Optional: Expected command output
                    "validation": {            # Optional: How to verify step completion
                        "type": string,        # e.g., "command_output", "command_success"
                        "command": string,     # Optional: Validation command
                        "success_pattern": string # Optional: Pattern to match in output
                    },
                    "hints": [                 # Optional: Array of helpful hints
                        string
                    ],
                    "cleanup": {               # Optional: Cleanup instructions
                        "command": string,     # Command to clean up resources
                        "description": string, # Explanation of cleanup
                        "required": boolean    # Whether cleanup is mandatory
                    }
                }
            ]
        }
    }
}

Example:
{
    "tutorials": {
        "s3": {
            "name": "S3 Basics",
            "description": "Learn basic S3 operations",
            "difficulty": "beginner",
            "variables": {
                "bucket-name": {
                    "description": "Name of the S3 bucket",
                    "validation_pattern": "^[a-z0-9.-]{3,63}$"
                }
            },
            "prerequisites": [
                {
                    "type": "permission",
                    "description": "s3:CreateBucket permission"
                }
            ],
            "steps": [
                {
                    "id": "create_bucket",
                    "title": "Creating your first bucket",
                    "description": "Let's create an S3 bucket",
                    "required": true,
                    "command": "aws s3 mb s3://{bucket-name}",
                    "command_validation": {
                        "pattern": "^aws s3 mb s3://[a-z0-9.-]{3,63}$",
                        "extract_vars": {
                            "bucket-name": "s3://([a-z0-9.-]{3,63})$"
                        }
                    },
                    "validation": {
                        "type": "command_output",
                        "command": "aws s3 ls",
                        "success_pattern": "{bucket-name}"
                    },
                    "hints": [
                        "Bucket names must be globally unique",
                        "Try using your username or timestamp in the name"
                    ],
                    "cleanup": {
                        "command": "aws s3 rb s3://{bucket-name}",
                        "description": "Remove the bucket we created",
                        "required": true
                    }
                },
                {
                    "id": "upload_file",
                    "title": "Uploading a file",
                    "description": "Upload a file to your bucket",
                    "required": false,
                    "depends_on": ["create_bucket"],
                    "command": "aws s3 cp example.txt s3://{bucket-name}/",
                    "command_validation": {
                        "pattern": "^aws s3 cp .+ s3://[a-z0-9.-]{3,63}/.*$",
                        "extract_vars": {
                            "file-name": "cp ([^ ]+) s3://"
                        }
                    },
                    "validation": {
                        "type": "command_output",
                        "command": "aws s3 ls s3://{bucket-name}/",
                        "success_pattern": "{file-name}"
                    },
                    "cleanup": {
                        "command": "aws s3 rm s3://{bucket-name}/{file-name}",
                        "description": "Remove the uploaded file",
                        "required": false
                    }
                }
            ]
        }
    }
}
"""
