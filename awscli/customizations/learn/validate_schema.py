def validate_schema(data, schema, path="root"):
    # Handle optional fields
    if isinstance(schema, tuple) and len(schema) == 2 and schema[0] == "optional":
        if data is None:
            return []
        return validate_schema(data, schema[1], path)

    # Handle dictionaries
    if isinstance(schema, dict):
        if not isinstance(data, dict):
            return [f"{path}: Expected dict, got {type(data).__name__}"]
        errors = []
        for key, subschema in schema.items():
            if key.startswith("<") and key.endswith(">"):
                # Handle pattern keys (like <variable-name>)
                if not isinstance(data, dict):
                    errors.append(f"{path}: Expected dict for pattern matching")
                    continue
                for subkey, subvalue in data.items():
                    errors.extend(validate_schema(subvalue, subschema, f"{path}.{subkey}"))
            else:
                # Regular keys
                is_optional = isinstance(subschema, tuple) and subschema[0] == "optional"
                if key not in data:
                    if not is_optional:
                        errors.append(f"{path}.{key}: Missing required key")
                else:
                    actual_schema = subschema[1] if is_optional else subschema
                    errors.extend(validate_schema(data[key], actual_schema, f"{path}.{key}"))
        return errors

    # Handle lists
    if isinstance(schema, list):
        if not isinstance(data, list):
            return [f"{path}: Expected list, got {type(data).__name__}"]
        if not schema:  # empty list schema matches any list
            return []
        errors = []
        for idx, item in enumerate(data):
            errors.extend(validate_schema(item, schema[0], f"{path}[{idx}]"))
        return errors

    # Handle type checking
    if isinstance(schema, type):
        if not isinstance(data, schema):
            return [f"{path}: Expected {schema.__name__}, got {type(data).__name__}"]
        return []

    return [f"{path}: Invalid schema definition"]


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
