Using this schema:
```python
TUTORIAL_SCHEMA = {
    "service": str,
    "name": str,
    "description": str,
    "credentials_required": ("optional", bool),
    "variables": ("optional", {
        "<variable-name>": {
            "description": str,
            "validation_pattern": str
        }
    }),
    "steps": [{
        "id": str,
        "title": str,
        "description": str,
        "required": ("optional", bool),
        "depends_on": ("optional", list),
        "command": str,
        "command_validation": ("optional", {
            "pattern": str,
            "extract_vars": ("optional", dict)
        }),
        "expected_output": ("optional", str),
        "validation": ("optional", {
            "type": str,
            "command": ("optional", str),
            "success_pattern": ("optional", str)
        }),
        "hints": ("optional", list),
        "cleanup": ("optional", {
            "command": str,
            "description": str,
            "required": ("optional", bool)
        })
    }]
}
```

And this example tutorial:
```json
{
  "service": "s3",
  "name": "S3 Basics",
  "description": "Learn basic S3 operations",
  "credentials_required": true,
  "variables": {
    "bucket-name": {
      "description": "Name of the S3 bucket",
      "validation_pattern": "^[a-z0-9.-]{3,63}$"
    }
  },
  "steps": [
    {
      "id": "create_bucket",
      "title": "Creating your first bucket",
      "description": "Let's create an S3 bucket",
      "command": "aws s3 mb s3://{bucket-name}",
      "command_validation": {
        "pattern": "^aws s3 mb s3://[a-z0-9.-]{3,63}$",
        "extract_vars": {
          "bucket-name": "s3://([a-z0-9.-]{3,63})$"
        }
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
      "id": "list_buckets",
      "title": "Listing buckets",
      "description": "Now let's list all your buckets",
      "required": true,
      "depends_on": ["create_bucket"],
      "command": "aws s3 ls",
      "validation": {
        "type": "command_success"
      }
    },
    {
      "id": "upload_file",
      "title": "Uploading a file",
      "description": "Let's upload a file to your new bucket",
      "required": false,
      "depends_on": ["create_bucket"],
      "command": "echo 'Hello S3' > hello.txt && aws s3 cp hello.txt s3://{bucket-name}/",
      "validation": {
        "type": "command_output",
        "command": "aws s3 ls s3://{bucket-name}/",
        "success_pattern": "hello.txt"
      },
      "cleanup": {
        "command": "aws s3 rm s3://{bucket-name}/hello.txt",
        "description": "Remove the uploaded file and local copy",
        "required": false
      }
    }
  ]
}
```

Create a tutorial for AWS DynamoDB that covers:
1. Creating a table
2. Adding an item
3. Querying items
4. Deleting the table

Follow the same structure and validation patterns as the S3 example.
